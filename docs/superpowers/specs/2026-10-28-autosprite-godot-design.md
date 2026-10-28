# Spec — Générateur local de sprites pixel art animés (inspiré d'AutoSprite)

- **Date :** 2026-10-28
- **Statut :** en relecture
- **Moteur cible MVP :** Godot 4 (via export PNG + JSON générique)

## 1. Contexte et objectif

[AutoSprite](https://www.autosprite.io/) transforme une image ou un prompt de personnage en spritesheets animées
(idle, walk, run, attaque…) exportables vers Godot, Unity, GameMaker, etc. Il génère une **vidéo** par IA puis la
découpe en frames, ce qui entraîne des nombres de frames variables et une dérive du personnage (reconnu dans leur FAQ).

Nous construisons un outil **interne** (usage personnel / équipe, pour nos propres jeux) qui fait la même chose,
spécialisé **pixel art**, fonctionnant **en local** sur le GPU de l'utilisateur, avec une approche **guidée par
poses** donnant un nombre de frames exact et des boucles propres.

### Critères de succès

1. À partir d'une image ou d'un prompt, produire un personnage pixel art animé en vue de dessus 4 directions
   (idle, walk, 4 attaques) en moins d'environ 30 min sur une RTX 4060 8 Go, retouches comprises.
2. Les sheets exportées s'importent dans Godot 4 sans retouche manuelle de découpe (frames alignées, ancrage stable).
3. Une frame ratée se corrige sans régénérer toute l'animation.
4. L'architecture permet d'ajouter une vue, une animation, un moteur IA ou un format d'export sans refonte.

## 2. Décisions de cadrage

| # | Sujet | Décision |
|---|-------|----------|
| 1 | Finalité | Outil interne, pas de comptes ni de facturation |
| 2 | Forme | Application web lancée en local, conçue pour être hébergeable plus tard |
| 3 | IA | Modèles locaux (ComfyUI). Hébergement GPU gratuit (Colab/Kaggle/HF) seulement en dépannage. Pas d'API payante |
| 4 | Matériel cible | Windows, GeForce RTX 4060 8 Go VRAM, 32 Go RAM |
| 5 | Style | Pixel art |
| 6 | Vues | Priorité : top-down 4 dir. (MVP) → side-view → 8 dir./isométrique |
| 7 | Animations MVP | idle, walk, attaque mains nues, épée, lance, arc |
| 8 | Armes | Dessinées dans le sprite (MVP), calque séparé plus tard. Arme visible seulement pendant l'attaque |
| 9 | Entrée | Image fournie **ou** prompt texte → image de référence validée |
| 10 | Export | PNG + JSON (générique, style Aseprite), pas de `.tres` dans le MVP |
| 11 | Paramètres | Taille de sortie et nombre de frames paramétrables ; FPS par animation |
| 12 | Sheets | Une sheet par animation, une ligne par direction (`down`, `left`, `right`, `up`) |
| 13 | Contrôle | Preview, régénération par frame/direction, réordonnancement, import de frame, réglages pixel art |
| 14 | Stack | Backend Python FastAPI, ComfyUI local (API HTTP/WS), frontend React + Vite + TypeScript |
| 15 | Approche de génération | Guidage par poses (ControlNet OpenPose + IP-Adapter), interface prévue pour un générateur vidéo ultérieur |

## 3. Architecture

```
Frontend React (Vite, TS)
   │  REST JSON + WebSocket (progression des jobs)
   ▼
Backend FastAPI
   ├── api/          routes REST + WS
   ├── jobs/         file de jobs (worker unique en mémoire, 1 job GPU à la fois)
   ├── domain/       modèles : Project, Character, View, Animation, Direction, Frame, PixelSettings
   ├── generation/   interface AnimationGenerator, ReferenceGenerator
   │     └── pose/   PoseGenerator + workflows ComfyUI (.json)
   ├── comfy/        client ComfyUI (HTTP + WS), vérification modèles/nœuds
   ├── poses/        bibliothèque de squelettes + interpolation + rendu
   ├── pixelart/     pipeline de post-traitement (CPU, déterministe)
   ├── export/       interface Exporter
   │     └── json_atlas/  PNG + JSON
   └── storage/      interface Storage (implémentation disque local)
          │
          ├──► ComfyUI (processus séparé, http://127.0.0.1:8188 par défaut)
          └──► dossier de données (DATA_DIR)
```

### Principes

- **Cœur indépendant du moteur de jeu et du moteur IA.** `domain/` ne dépend ni de Godot ni de ComfyUI.
  Nouveau moteur de jeu = nouvel `Exporter` ; générateur vidéo = nouvel `AnimationGenerator`.
- **Jobs asynchrones.** Toute opération GPU est un job. MVP : worker unique en mémoire (asyncio), une file FIFO.
  L'interface `JobQueue` permet de passer à Redis/RQ pour l'hébergement.
- **Stockage fichiers, sans base de données.** Un dossier par projet ; `project.json` est la source de vérité.
- **Pixel art en CPU** (Pillow + numpy), fonctions pures, testables sans GPU.
- **Configuration** par variables d'environnement / `.env` (`COMFY_URL`, `DATA_DIR`, noms des modèles…).
- **Hébergeable plus tard** : pas de chemins en dur, stockage et file derrière interfaces, tout passe par l'API.
  Pas d'authentification dans le MVP.

### Interfaces clés (Python, indicatif)

```python
class ReferenceGenerator(Protocol):
    async def from_prompt(self, prompt: str, n: int, seed: int) -> list[Image]: ...
    async def remove_background(self, image: Image) -> Image: ...
    async def turnaround(self, reference: Image, view: ViewKind, seed: int) -> dict[Direction, Image]: ...

class AnimationGenerator(Protocol):
    async def generate(self, ref: Image, poses: list[Pose], style_prompt: str, seed: int,
                       progress: ProgressCallback) -> list[Image]: ...
    async def regenerate_frame(self, ref: Image, poses: list[Pose], frames: list[Image],
                               index: int, style_prompt: str, seed: int,
                               progress: ProgressCallback) -> Image: ...

class Exporter(Protocol):
    def export(self, project: Project, processed: ProcessedFrames, out: Path) -> Path: ...

class Storage(Protocol):
    def read_json(self, key: str) -> dict: ...
    def write_json(self, key: str, data: dict) -> None: ...   # écriture atomique
    def read_image(self, key: str) -> Image: ...
    def write_image(self, key: str, img: Image) -> None: ...
```

## 4. Modèle de données

### Arborescence d'un projet

```
DATA_DIR/projects/<project_id>/
  project.json
  reference/
    input.png            # image importée ou générée retenue
    reference.png        # détourée, validée
    candidates/          # propositions issues du prompt
  views/
    down.png left.png right.png up.png
  animations/<anim_id>/<direction>/
    raw/000.png 001.png …          # sortie IA brute (conservée)
    processed/000.png …            # après pipeline pixel art (régénérable)
  exports/<timestamp>.zip
```

### `project.json` (extrait)

```json
{
  "id": "knight-01",
  "name": "Chevalier",
  "view": "topdown4",
  "style_prompt": "pixel art, 16-bit rpg character",
  "seed": 1234,
  "output_size": 64,
  "pixel_settings": {
    "palette": { "mode": "auto", "colors": 24 },
    "outline": { "enabled": true, "color": "#1a1a1a" },
    "alpha_threshold": 128
  },
  "reference": { "status": "validated" },
  "views": { "down": "validated", "left": "validated", "right": "validated", "up": "pending" },
  "animations": [
    {
      "id": "attack_sword",
      "type": "attack_sword",
      "frame_count": 6,
      "fps": 12,
      "loop": false,
      "directions": {
        "down": { "frames": ["000.png", "001.png", "002.png", "003.png", "004.png", "005.png"] }
      }
    }
  ]
}
```

`palette.mode` ∈ `auto` (k-means commun à tout le personnage) | `preset` (`pico8`, `db32`, `endesga32`…) | `custom`
(fichier `.hex`/`.gpl` importé).

## 5. Parcours utilisateur

1. **Création du projet** : nom, taille de sortie (défaut 64 px), palette, style.
2. **Référence** :
   - *Image* : upload PNG/JPG → détourage automatique.
   - *Texte* : prompt → 4 propositions → choix ou relance.
   - L'utilisateur valide l'image de référence.
3. **Vues 4 directions** : génération en une passe (4 poses neutres en grille, guidée par la référence via
   IP-Adapter). Chaque vue est validable / régénérable individuellement. Option « right = miroir de left »
   (désactivée par défaut, car elle inverse les éléments asymétriques).
4. **Animations** : sélection parmi idle, walk, attack_unarmed, attack_sword, attack_spear, attack_bow ;
   réglage du nombre de frames et du FPS. Un job par (animation × direction), utilisant la vue de la direction
   comme référence.
5. **Revue** : grille animations × directions, preview en boucle (taille réelle et zoom ×4).
   - Par frame : régénérer, supprimer, réordonner, remplacer par un PNG importé.
   - Par animation : régénérer une ou toutes les directions, changer FPS / nombre de frames.
   - Réglages pixel art en direct : recalcul depuis `raw/`, sans IA.
6. **Export** : ZIP téléchargeable (cf. §8).

## 6. Bibliothèque de poses

- Format : squelette OpenPose 18 points clés (COCO) en coordonnées normalisées [0, 1].
- Fichier : `poses/<view>/<animation>/<direction>.json` contenant des **keyframes** :

```json
{
  "loop": true,
  "keyframes": [
    { "t": 0.0,  "points": [[0.50, 0.12], [0.50, 0.25], "…18 points…"] },
    { "t": 0.5,  "points": ["…"] }
  ]
}
```

- **Interpolation** : pour N frames, échantillonnage à `t = i / N` (animation en boucle) ou `t = i / (N - 1)`
  (animation sans boucle), interpolation linéaire des points entre keyframes. Un point absent (occlusion)
  reste absent tant qu'il l'est dans l'une des deux keyframes encadrantes.
- **Rendu** : squelette dessiné par notre code (couleurs standard OpenPose, fond noir), pas de préprocesseur.
- **MVP** : `topdown4` × {idle, walk, attack_unarmed, attack_sword, attack_spear, attack_bow} × {down, left, right, up},
  plus une pose neutre par direction pour les vues.
- **Limite connue** : en vue de dessus, OpenPose rend mal la profondeur (ex. attaque vers le haut). Ces
  combinaisons demanderont plus de régénérations.

## 7. Génération (PoseGenerator)

1. Composer une grille de poses (ex. 3×2 pour 6 frames) dans un canevas d'environ 1024 px de côté, une case par frame,
   fond uni.
2. Remplir un workflow ComfyUI modèle (`generation/pose/workflows/*.json`) : checkpoint SDXL + LoRA pixel art,
   IP-Adapter (image de référence de la direction), ControlNet OpenPose (grille de poses), KSampler, seed.
3. Soumettre via `POST /prompt`, suivre la progression via le WebSocket ComfyUI, récupérer l'image.
4. Découper selon la grille → frames brutes (`raw/`).
5. **Régénération d'une frame** : workflow d'inpainting, avec un masque sur la seule case cible et les autres frames
   visibles comme contexte.

- **Modèles par défaut** (configurables dans `.env`) : checkpoint SDXL, LoRA pixel art SDXL, IP-Adapter Plus SDXL,
  ControlNet OpenPose SDXL, modèle de détourage (nœud RMBG/BiRefNet). Repli SD 1.5 documenté si la VRAM ou la vitesse
  posent problème.
- Les workflows sont versionnés et modifiables dans ComfyUI. Les nœuds personnalisés requis sont listés dans le
  guide d'installation.
- Texte vers image pour la référence : même checkpoint, workflow simple avec 4 images par lot.

## 8. Pipeline pixel art et export

### Pipeline (`pixelart/`, fonctions pures, appliquées par animation)

1. **Détourage** : alpha issu du modèle de détourage, ou clé de couleur sur le fond uni.
2. **Rognage et ancrage** : boîte englobante commune à toutes les frames de l'animation (toutes directions) ;
   pieds alignés sur un point d'ancrage fixe (bas-centre), pour éviter le tremblement.
3. **Réduction** vers `output_size` : réduction par moyenne des blocs puis plus proche voisin.
4. **Quantification** : palette commune à tout le personnage (`auto` = k-means sur l'ensemble des frames) ou
   palette imposée ; pas de tramage par défaut.
5. **Alpha binaire** (`alpha_threshold`).
6. **Contour optionnel** de 1 px.

### Export (`export/json_atlas/`)

ZIP contenant :

```
<character>/
  character.json
  idle.png            idle.json
  walk.png            walk.json
  attack_unarmed.png  attack_unarmed.json
  attack_sword.png    attack_sword.json
  attack_spear.png    attack_spear.json
  attack_bow.png      attack_bow.json
  godot/load_spriteframes.gd   # script utilitaire : JSON → SpriteFrames
```

- **Sheet** : une par animation ; lignes = directions dans l'ordre `down, left, right, up` ; colonnes = frames ;
  cellules de `output_size` × `output_size` ; pas de padding (option `padding` en paramètre, 0 par défaut).
- **JSON d'animation**, compatible avec la structure d'Aseprite (`frames` + `meta`), complétée de nos clés :

```json
{
  "frames": {
    "attack_sword_down_0": { "frame": { "x": 0, "y": 0, "w": 64, "h": 64 }, "duration": 83 }
  },
  "meta": {
    "image": "attack_sword.png",
    "size": { "w": 384, "h": 256 },
    "frameTags": [
      { "name": "attack_sword_down", "from": 0, "to": 5, "direction": "forward" }
    ],
    "x_autosprite": {
      "animation": "attack_sword",
      "fps": 12,
      "loop": false,
      "frame_size": 64,
      "anchor": { "x": 32, "y": 60 },
      "rows": ["down", "left", "right", "up"]
    }
  }
}
```

- `character.json` : nom, vue, taille, ancrage, liste des animations et de leurs fichiers.
- Convention de nommage des animations : `<animation>_<direction>` (ex. `walk_left`).
- `load_spriteframes.gd` : script GDScript (Godot 4.2+) qui lit un JSON et construit un `SpriteFrames`
  (un `AtlasTexture` par frame, FPS et boucle appliqués). Il n'est pas obligatoire, il évite juste le travail manuel.

## 9. API (backend)

| Méthode | Route | Rôle |
|---------|-------|------|
| GET | `/api/health` | État du backend + ComfyUI + modèles/nœuds manquants |
| GET/POST | `/api/projects` | Lister / créer |
| GET/PATCH/DELETE | `/api/projects/{id}` | Lire / modifier les réglages / supprimer |
| POST | `/api/projects/{id}/reference/upload` | Importer une image |
| POST | `/api/projects/{id}/reference/generate` | Prompt → job de propositions |
| POST | `/api/projects/{id}/reference/select` | Choisir et valider la référence |
| POST | `/api/projects/{id}/views/generate` | Job : 4 vues (ou une seule via `direction`) |
| POST | `/api/projects/{id}/views/{dir}/validate` | Valider une vue |
| POST | `/api/projects/{id}/animations` | Ajouter / configurer des animations |
| POST | `/api/projects/{id}/animations/{anim}/generate` | Job(s) par direction |
| POST | `/api/projects/{id}/animations/{anim}/{dir}/frames/{i}/regenerate` | Job : une frame |
| PUT | `/api/projects/{id}/animations/{anim}/{dir}/frames` | Ordre / suppression des frames |
| POST | `/api/projects/{id}/animations/{anim}/{dir}/frames/{i}/import` | Remplacer une frame par un PNG |
| GET | `/api/projects/{id}/preview/{anim}/{dir}` | Frames traitées (après réglages) |
| POST | `/api/projects/{id}/export` | Générer le ZIP |
| GET | `/api/jobs` · `/api/jobs/{id}` · DELETE `/api/jobs/{id}` | Suivi / annulation |
| WS | `/api/ws` | Événements : progression des jobs, mises à jour du projet |

Erreurs : format uniforme `{ "error": { "code": "...", "message": "...", "hint": "..." } }`.

## 10. Frontend

React + Vite + TypeScript ; écrans :

1. **Projets** : liste, création.
2. **Référence** : import ou prompt, choix parmi les propositions, validation.
3. **Vues** : 4 vues, régénération et validation une par une.
4. **Animations** : sélection, réglage frames et FPS, lancement.
5. **Revue** : grille animations × directions, aperçu animé (canvas, `image-rendering: pixelated`), actions par frame,
   panneau des réglages pixel art.
6. **Export**.

Un panneau permanent montre la file des jobs et un bandeau l'état de ComfyUI.

## 11. Gestion des erreurs

- **ComfyUI indisponible, modèle ou nœud manquant** : vérification au démarrage et avant chaque job ; bandeau
  explicite qui nomme l'élément manquant et l'endroit où il est attendu.
- **Mémoire GPU saturée** : l'erreur est récupérée, le job passe en `failed` avec un conseil (moins de frames par
  grille, résolution réduite, repli SD 1.5) ; relance en un clic.
- **Jobs** : `queued`, `running`, `succeeded`, `failed` ou `cancelled` ; une annulation propage l'interruption à
  ComfyUI (`/interrupt`). Au redémarrage, un job resté `running` passe en `failed`.
- **Écritures atomiques** (fichier temporaire puis renommage) pour `project.json` et les images.
- **Validation** des entrées par Pydantic (formats, tailles, bornes de `frame_count` 2–16 et de `output_size` 16–256).

## 12. Tests

- **pixelart/** : tests unitaires déterministes (pytest) sur des images fixtures : détourage, ancrage, réduction,
  quantification, contour.
- **poses/** : interpolation (nombre de frames, boucle ou non, points masqués), rendu comparé à des images de référence.
- **export/** : structure du PNG (dimensions, position des cellules) et du JSON (validation de schéma).
  Test optionnel : Godot en mode sans interface lance `load_spriteframes.gd` sur un export (ignoré si Godot est absent).
- **generation/** et **jobs/** : `FakeComfyClient` qui renvoie des images fixes, pour tester le parcours complet sans GPU.
- **Test de bout en bout réel** avec ComfyUI, marqué `@pytest.mark.gpu` et lancé seulement à la demande.
- **Frontend** : Vitest sur la logique (timing de l'aperçu, état de la grille). Pas de tests de bout en bout dans le MVP.

## 13. Installation et lancement (Windows)

- Prérequis : Python 3.11+, Node 20+, ComfyUI portable pour Windows.
- `docs/setup-comfyui.md` : nœuds personnalisés à installer, modèles à télécharger et dossiers de destination.
- `.env.example` documenté.
- `start.bat` : lance le backend (uvicorn) et le frontend (vite) ; vérifie que ComfyUI répond.

## 14. Hors périmètre du MVP (ordre indicatif)

1. Vue de côté (`side`), puis 8 directions et isométrique.
2. Animations supplémentaires : run, hurt, death, cast, jump, roll…
3. Arme sur un calque séparé, avec la position de la main par frame.
4. `VideoGenerator` (FramePack) et animations libres décrites par un prompt.
5. Exports spécifiques par moteur : `.tres` Godot, Unity, GameMaker…
6. Hébergement : authentification, stockage S3, file Redis, GPU distant (Colab, Kaggle ou HF en dépannage).
7. Éditeur de pixels intégré (l'aller-retour avec Aseprite suffit pour l'instant).

## 15. Risques

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Cohérence du personnage entre frames ou directions | Élevé | Grille en une passe, IP-Adapter sur la vue de la direction, palette commune, régénération par frame en inpainting |
| Poses top-down peu lisibles pour OpenPose | Moyen | Keyframes ajustées à la main, régénération ciblée ; repli possible vers une autre ControlNet (depth, lineart) dans une version ultérieure |
| VRAM 8 Go limite pour SDXL + ControlNet + IP-Adapter | Moyen | Déchargement par ComfyUI, grilles de taille raisonnable, repli SD 1.5 |
| Qualité du « vrai » pixel art après réduction | Moyen | Réduction par moyenne des blocs, palette réduite, contour ; LoRA pixel art |
| Évolution des nœuds ComfyUI | Faible | Versions documentées, vérification au démarrage |
