# PixelForge

Application locale qui transforme un personnage (image ou description) en **animations de sprites pixel art**
(idle, marche, attaques) vues de dessus dans 4 directions, via un **ComfyUI local**, puis les exporte en
**PNG + JSON** prêts pour **Godot 4**.

- Backend : FastAPI (`backend/`) · Frontend : React + Vite (`frontend/`)
- Conception détaillée : `docs/superpowers/specs/2026-10-28-autosprite-godot-design.md`

## Prérequis

- Windows 10/11, GPU NVIDIA (testé visé : RTX 4060 8 Go), 32 Go de RAM conseillés
- Python 3.11+ (le lanceur `py -3.11` est utilisé s'il existe) et Node.js 18+
- ComfyUI avec ses nœuds et modèles : suivez **`docs/setup-comfyui.md`** (non requis pour le mode démo)

## Démarrage rapide

1. Installez et lancez ComfyUI (`docs/setup-comfyui.md`).
2. (Optionnel) copiez `.env.example` en `.env` et ajustez-le.
3. Double-cliquez sur **`start.bat`**. Au premier lancement il crée `backend\.venv`, installe les dépendances
   Python et `npm`, puis ouvre deux fenêtres (backend sur le port 8000, frontend sur le port 5173) et le
   navigateur sur <http://localhost:5173>.

Si ComfyUI ne répond pas, `start.bat` affiche un avertissement mais continue. Le bandeau de l'application
indique les nœuds ou modèles manquants.

## Mode démo (sans GPU)

Pour essayer l'interface sans ComfyUI, mettez dans `.env` :

```
PIXELFORGE_FAKE_COMFY=1
```

Un faux générateur produit des sprites factices : utile pour découvrir le parcours et tester l'export.

## Configuration

Toutes les variables `PIXELFORGE_*` sont décrites dans `.env.example`. Attention : `PIXELFORGE_CORS_ORIGINS`
doit être une **liste JSON**, par exemple `["http://localhost:5173"]`.

## Utilisation dans Godot

L'export est un ZIP : `<personnage>/character.json`, une sheet `<animation>.png` + `<animation>.json` par
animation, et `godot/load_spriteframes.gd`.

1. Décompressez le ZIP dans votre projet Godot 4.2+ (par exemple `res://hero/`).
2. Copiez `load_spriteframes.gd` dans le projet et **adaptez le chemin du `preload`** à son emplacement.
3. Dans **Project Settings → Rendering → Textures → Default Texture Filter**, choisissez **Nearest** pour
   conserver des pixels nets.
4. Dans un script :

```gdscript
var frames := preload("res://load_spriteframes.gd").build("res://hero/walk.json")
$AnimatedSprite2D.sprite_frames = frames
$AnimatedSprite2D.play("walk_down")
```

Une animation Godot est créée par balise de frame (*frame tag*), nommée `<animation>_<direction>`
(`walk_down`, `walk_left`, `walk_right`, `walk_up`), avec le FPS et la boucle enregistrés dans l'export.

## Tests

Depuis `backend/`, avec le venv activé (`backend\.venv\Scripts\activate`) :

```
pytest                # tests par défaut (sans GPU ni Godot)
pytest -m gpu         # parcours complet avec le vrai ComfyUI (prompt -> export)
pytest -m godot       # chargement dans Godot sans interface (exécutable Godot requis)
ruff check src tests
```

`pytest -m gpu` **échoue** avec le message `comfy_unreachable` si ComfyUI ne répond pas ; il est long
(plusieurs minutes, chargement des modèles inclus). Frontend : `cd frontend && npm test` et `npm run build`.

## Limites connues

- **Workflows non vérifiés** : écrits sans ComfyUI en ligne, ils doivent être ouverts une première fois dans
  ComfyUI (`docs/setup-comfyui.md`, § 4) ; tant qu'un vrai essai n'a pas eu lieu, des ajustements sont probables.
- **Vue de dessus, direction `up`** : les poses de dos ne portent pas de points clés de tête ; ControlNet peut
  « perdre » la tête. Régénérez les frames concernées.
- **Cohérence des sprites** non garantie d'une frame à l'autre : utilisez la régénération frame par frame
  dans l'écran de revue.
- Mémoire GPU limitée (8 Go) : voir les conseils `--lowvram` dans `docs/setup-comfyui.md`.
