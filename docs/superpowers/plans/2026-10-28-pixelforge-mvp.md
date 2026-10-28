# PixelForge MVP — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** une application web locale qui transforme une image ou un prompt en personnage pixel art animé
(top-down 4 directions : idle, walk, 4 attaques) et l'exporte en PNG + JSON pour Godot 4.

**Architecture :** un backend FastAPI orchestre ComfyUI (processus local séparé) via des workflows JSON
paramétrés. La génération est guidée par poses (ControlNet OpenPose + IP-Adapter), avec toutes les frames
d'une animation générées sur une seule grille. Un pipeline pixel art CPU déterministe transforme les frames
brutes, et un exporteur produit les sheets. Un frontend React pilote le tout et suit les jobs par WebSocket.

**Stack :** Python 3.11, FastAPI, Pydantic v2, pydantic-settings, Pillow, numpy, httpx, websockets, pytest,
pytest-asyncio ; React 18 + Vite + TypeScript, Vitest ; ComfyUI (nœuds ComfyUI_IPAdapter_plus, ComfyUI-RMBG).

**Spec :** `docs/superpowers/specs/2026-10-28-autosprite-godot-design.md`

## Contraintes globales

- Plateforme cible : Windows, RTX 4060 8 Go VRAM, 32 Go RAM. Tout le code et les chemins doivent fonctionner
  sous Windows (`pathlib`, pas de séparateurs en dur, `start.bat`).
- Python ≥ 3.11, Node ≥ 20, Godot ≥ 4.2 pour le script fourni.
- Nom du paquet Python : `pixelforge` (dans `backend/src/pixelforge`). Frontend dans `frontend/`.
- Directions et ordre des lignes de sheet : `down, left, right, up`.
- Animations MVP : `idle, walk, attack_unarmed, attack_sword, attack_spear, attack_bow` ; vue `topdown4`.
- Bornes : `frame_count` 2–16, `output_size` 16–256, `alpha_threshold` 0–255, `fps` 1–60, `palette.colors` 2–64.
- Défauts : `output_size` 64 ; idle 4 frames / 6 fps / boucle ; walk 6 / 10 / boucle ; attaques 6 / 12 / sans boucle.
- Nommage des animations exportées : `<animation>_<direction>` ; clés de frame `<animation>_<direction>_<i>`.
- Erreurs API : `{ "error": { "code": str, "message": str, "hint": str | null } }`.
- Écritures de fichiers atomiques (fichier temporaire puis `os.replace`).
- Configuration par variables d'environnement préfixées `PIXELFORGE_` et `.env`.
- Un seul job GPU à la fois.
- Aucun appel à un service payant ; aucune authentification.
- Les tests par défaut n'exigent ni GPU ni ComfyUI ni Godot (`-m "not gpu"` est le défaut).

## Points de vigilance (Review Focus)

1. **Image importée atypique** (JPG sans alpha, PNG déjà transparent, très grande, non carrée, mode `P`/`LA`) :
   elle doit être normalisée en RGBA, réduite à 1024 px de côté max, et ne jamais faire planter le détourage.
   → test dans la tâche 12 (`test_upload_normalizes_odd_images`).
2. **Frame vide après détourage** (fond identique au personnage, frame entièrement transparente) : le pipeline
   doit produire une frame transparente, pas d'exception. → test dans la tâche 6 (`test_common_bbox_all_empty`)
   et 7 (`test_process_animation_with_empty_frame`).
3. **`frame_count` modifié après génération** : les directions existantes passent à `stale`, l'aperçu montre
   encore les anciennes frames, l'export refuse avec un message clair. → tâche 12 (`test_frame_count_change_marks_stale`)
   et tâche 8 (`test_export_rejects_incomplete`).
4. **Deux jobs sur la même cible** (régénérer une frame pendant que la direction est en génération) : refus 409
   `conflict`, pas d'écrasement. → tâche 12 (`test_conflicting_job_rejected`).
5. **Lignes de longueurs différentes** (l'utilisateur a supprimé une frame dans une seule direction) : la sheet
   prend la largeur du max, les `frameTags` restent exacts. → tâche 8 (`test_sheet_uneven_rows`).

---

## Structure des fichiers

```
backend/
  pyproject.toml
  src/pixelforge/
    __init__.py
    config.py                 # Settings, get_settings()
    domain/models.py          # enums + modèles Pydantic du projet
    storage/base.py           # Protocol Storage
    storage/local.py          # LocalStorage (écritures atomiques)
    storage/keys.py           # fonctions de chemins
    storage/projects.py       # ProjectRepository
    grid.py                   # grid_shape, compose_grid, split_grid
    poses/model.py            # Pose, Keyframe, PoseClip, sample()
    poses/render.py           # render_pose()
    poses/library.py          # load_clip(), load_neutral(), list_clips()
    poses/data/topdown4/<anim>/<dir>.json, neutral/<dir>.json
    pixelart/steps.py         # étapes unitaires
    pixelart/palettes.py      # presets, parse, k-means
    pixelart/pipeline.py      # process_animation(), character_palette()
    export/sheet.py           # build_sheet(), build_animation_json(), build_character_json()
    export/json_atlas.py      # JsonAtlasExporter
    export/godot/load_spriteframes.gd
    comfy/client.py           # Protocol ComfyClient, HttpComfyClient, ComfyError
    comfy/fake.py             # FakeComfyClient
    comfy/workflows.py        # load_workflow, bind, required_nodes
    comfy/health.py           # check_comfy, HealthReport
    generation/base.py        # Protocols ReferenceGenerator, AnimationGenerator, GenerationError
    generation/reference.py   # ComfyReferenceGenerator
    generation/pose_generator.py  # PoseGenerator
    generation/workflows/{txt2img,remove_bg,turnaround,pose_grid,pose_inpaint}.json
    jobs/events.py            # EventBus
    jobs/queue.py             # Job, JobStatus, JobQueue, JobContext
    services/projects.py      # ProjectService (orchestration)
    services/images.py        # normalize_upload()
    api/app.py                # create_app()
    api/errors.py             # ApiError + handlers
    api/routes/*.py           # health, projects, reference, views, animations, jobs, files, export, ws
  tests/ (miroir de src)
frontend/
  package.json, vite.config.ts, tsconfig.json, index.html
  src/api/{types.ts,client.ts}
  src/hooks/useEvents.ts
  src/lib/{playback.ts,review.ts}
  src/components/{StatusBanner,JobsPanel,SpritePlayer}.tsx
  src/pages/{ProjectsPage,ReferencePage,ViewsPage,AnimationsPage,ReviewPage,ExportPage}.tsx
  src/App.tsx, src/main.tsx
docs/setup-comfyui.md
.env.example
start.bat
```

---

### Task 1: Squelette backend et configuration

**Files:**
- Create: `backend/pyproject.toml`, `backend/src/pixelforge/__init__.py`, `backend/src/pixelforge/config.py`, `.gitignore`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings, préfixe `PIXELFORGE_`, `.env`) avec les champs
  `comfy_url: str = "http://127.0.0.1:8188"`, `data_dir: Path = Path("data")`,
  `checkpoint: str = "sd_xl_base_1.0.safetensors"`, `lora: str = "pixel-art-xl.safetensors"`,
  `lora_strength: float = 1.0`, `controlnet_openpose: str = "controlnet-openpose-sdxl-1.0.safetensors"`,
  `ipadapter_preset: str = "PLUS (high strength)"`, `grid_canvas: int = 1024`, `cors_origins: list[str] = ["http://localhost:5173"]` ;
  `get_settings() -> Settings` (mis en cache).

- [ ] **Step 1 :** `pyproject.toml` (hatchling, src-layout), dépendances runtime : fastapi, uvicorn[standard],
  pydantic>=2, pydantic-settings, pillow, numpy, httpx, websockets, python-multipart ; dev : pytest, pytest-asyncio,
  ruff. Config pytest : `asyncio_mode = "auto"`, marqueurs `gpu`, `godot`, `addopts = "-m 'not gpu and not godot'"`.
  `.gitignore` : `data/`, `.env`, `__pycache__/`, `node_modules/`, `dist/`, `.venv/`.
- [ ] **Step 2 : test qui échoue**

```python
def test_defaults(monkeypatch):
    monkeypatch.delenv("PIXELFORGE_COMFY_URL", raising=False)
    s = Settings()
    assert s.comfy_url == "http://127.0.0.1:8188"
    assert s.grid_canvas == 1024

def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELFORGE_DATA_DIR", str(tmp_path))
    assert Settings().data_dir == tmp_path
```

- [ ] **Step 3 :** `cd backend && pip install -e .[dev] && pytest tests/test_config.py -v` → FAIL (import).
- [ ] **Step 4 :** implémenter `config.py`.
- [ ] **Step 5 :** `pytest -v` → PASS ; `ruff check src tests` → propre.
- [ ] **Step 6 :** commit `feat(backend): squelette et configuration`.

---

### Task 2: Modèle de domaine

**Files:**
- Create: `backend/src/pixelforge/domain/__init__.py`, `backend/src/pixelforge/domain/models.py`
- Test: `backend/tests/domain/test_models.py`

**Interfaces:**
- Produces :
  - `Direction(StrEnum)` : `down, left, right, up` ; `DIRECTION_ORDER: tuple[Direction, ...]` dans cet ordre.
  - `ViewKind(StrEnum)` : `topdown4`.
  - `AnimationType(StrEnum)` : `idle, walk, attack_unarmed, attack_sword, attack_spear, attack_bow`.
  - `AnimationDefaults(frame_count: int, fps: int, loop: bool)` ; `DEFAULT_ANIMATIONS: dict[AnimationType, AnimationDefaults]`
    (valeurs des contraintes globales).
  - `PaletteSettings(mode: Literal["auto","preset","custom"]="auto", colors: int=24, preset: str|None=None, custom_colors: list[str]|None=None)`
    — validateur : `preset` requis si `mode="preset"`, `custom_colors` (hex `#rrggbb`, ≥2) requis si `mode="custom"`.
  - `OutlineSettings(enabled: bool=False, color: str="#1a1a1a")`.
  - `PixelSettings(palette: PaletteSettings, outline: OutlineSettings, alpha_threshold: int=128, padding: int=0)`.
  - `DirectionState(frames: list[str]=[], status: Literal["empty","generating","ready","stale"]="empty")`.
  - `AnimationConfig(id: str, type: AnimationType, frame_count: int, fps: int, loop: bool, directions: dict[Direction, DirectionState])`
    ; `AnimationConfig.from_type(t: AnimationType) -> AnimationConfig` (id = valeur du type, 4 directions vides).
  - `ReferenceState(status: Literal["none","candidates","validated"]="none", candidates: list[str]=[])`.
  - `ViewStatus = Literal["pending","generated","validated"]`.
  - `Project(id: str, name: str, view: ViewKind=topdown4, style_prompt: str="pixel art, 16-bit rpg character, top-down view",
    seed: int, output_size: int=64, pixel_settings: PixelSettings, reference: ReferenceState, views: dict[Direction, ViewStatus],
    mirror_right: bool=False, animations: list[AnimationConfig]=[])` ; méthode `animation(anim_id: str) -> AnimationConfig`
    (lève `KeyError`) ; `anchor() -> tuple[int, int]` = `(output_size // 2, output_size - max(1, output_size // 16))`.

- [ ] **Step 1 : tests qui échouent**

```python
def test_bounds():
    base = AnimationConfig.from_type(AnimationType.walk).model_dump()
    with pytest.raises(ValidationError): AnimationConfig.model_validate({**base, "frame_count": 1})
    with pytest.raises(ValidationError): AnimationConfig.model_validate({**base, "frame_count": 17})
    with pytest.raises(ValidationError): make_project(output_size=8)
    with pytest.raises(ValidationError): make_project(output_size=512)

def test_defaults_from_type():
    a = AnimationConfig.from_type(AnimationType.attack_bow)
    assert (a.frame_count, a.fps, a.loop) == (6, 12, False)
    assert list(a.directions) == list(DIRECTION_ORDER)

def test_palette_validation():
    with pytest.raises(ValidationError): PaletteSettings(mode="preset")
    with pytest.raises(ValidationError): PaletteSettings(mode="custom", custom_colors=["#fff"])

def test_anchor():
    assert make_project(output_size=64).anchor() == (32, 60)

def test_roundtrip_json():
    p = make_project(); assert Project.model_validate_json(p.model_dump_json()) == p
```

(`make_project` est un helper du fichier de test qui remplit les champs obligatoires.)

- [ ] **Step 2 :** `pytest tests/domain -v` → FAIL.
- [ ] **Step 3 :** implémenter `models.py` (bornes via `Field(ge=, le=)`).
- [ ] **Step 4 :** `pytest tests/domain -v` → PASS.
- [ ] **Step 5 :** commit `feat(domain): modèles du projet`.

---

### Task 3: Stockage local et dépôt de projets

**Files:**
- Create: `storage/base.py`, `storage/local.py`, `storage/keys.py`, `storage/projects.py` (sous `backend/src/pixelforge/`)
- Test: `backend/tests/storage/test_local.py`, `backend/tests/storage/test_projects.py`

**Interfaces:**
- Consumes : `Project`, `PixelSettings`, `ReferenceState`, `DIRECTION_ORDER` (Task 2).
- Produces :
  - `Storage` (Protocol) : `read_bytes(key) -> bytes`, `write_bytes(key, data) -> None`, `read_json(key) -> dict`,
    `write_json(key, data) -> None`, `read_image(key) -> Image.Image` (converti RGBA), `write_image(key, img) -> None` (PNG),
    `exists(key) -> bool`, `delete(key) -> None`, `delete_prefix(prefix) -> None`, `list(prefix) -> list[str]` (triée),
    `path(key) -> Path`. Les clés utilisent `/`.
  - `LocalStorage(root: Path)` ; lève `ValueError` si une clé sort de `root` (`..`).
  - `keys.py` : `project_json(pid)`, `reference_input(pid)`, `reference_image(pid)`, `candidate(pid, i)`,
    `view_image(pid, d)`, `raw_dir(pid, anim, d)`, `raw_frame(pid, anim, d, name)`, `processed_frame(pid, anim, d, name)`,
    `export_zip(pid, stamp)` — chemins exactement ceux de la spec §4.
  - `ProjectRepository(storage)` : `create(name: str, output_size: int = 64, style_prompt: str | None = None) -> Project`
    (id = slug du nom + suffixe 4 caractères hex, seed aléatoire, `views` tous `pending`), `get(pid) -> Project`
    (lève `ProjectNotFound`), `save(project)`, `list() -> list[Project]`, `delete(pid)`.

- [ ] **Step 1 : tests qui échouent**

```python
def test_atomic_write_leaves_no_temp(tmp_path):
    s = LocalStorage(tmp_path); s.write_json("a/b.json", {"x": 1})
    assert s.read_json("a/b.json") == {"x": 1}
    assert [p.name for p in (tmp_path / "a").iterdir()] == ["b.json"]

def test_rejects_escape(tmp_path):
    with pytest.raises(ValueError): LocalStorage(tmp_path).write_bytes("../x", b"")

def test_image_roundtrip_rgba(tmp_path): ...  # écrit RGB, relit en mode "RGBA"

def test_create_get_list_delete(tmp_path):
    repo = ProjectRepository(LocalStorage(tmp_path))
    p = repo.create("Chevalier Bleu")
    assert p.id.startswith("chevalier-bleu-")
    assert repo.get(p.id) == p and [x.id for x in repo.list()] == [p.id]
    repo.delete(p.id)
    with pytest.raises(ProjectNotFound): repo.get(p.id)
```

- [ ] **Step 2 :** `pytest tests/storage -v` → FAIL.
- [ ] **Step 3 :** implémenter (écriture : `tempfile.NamedTemporaryFile(dir=parent, delete=False)` puis `os.replace`).
- [ ] **Step 4 :** `pytest tests/storage -v` → PASS.
- [ ] **Step 5 :** commit `feat(storage): stockage local et dépôt de projets`.

---

### Task 4: Grilles, modèle de pose, interpolation et rendu

**Files:**
- Create: `grid.py`, `poses/__init__.py`, `poses/model.py`, `poses/render.py`
- Test: `backend/tests/test_grid.py`, `backend/tests/poses/test_model.py`, `backend/tests/poses/test_render.py`

**Interfaces:**
- Produces :
  - `grid_shape(n: int) -> tuple[int, int]` : `cols = ceil(sqrt(n))`, `rows = ceil(n / cols)`.
  - `cell_size(n: int, canvas: int) -> int` : `canvas // max(cols, rows)` arrondi au multiple de 8 inférieur.
  - `compose_grid(images: list[Image], cell: int, background=(0,0,0)) -> Image` : chaque image redimensionnée à `cell`
    (contain, centrée), ordre ligne par ligne.
  - `split_grid(image: Image, n: int) -> list[Image]` : inverse (déduit `cell` de la largeur / cols).
  - `cell_box(index: int, n: int, cell: int) -> tuple[int, int, int, int]`.
  - `Pose(points: list[tuple[float, float] | None])` (exactement 18 entrées, coordonnées dans [0, 1]).
  - `Keyframe(t: float, points: ...)`, `PoseClip(loop: bool, keyframes: list[Keyframe])` (t triés, premier = 0).
  - `sample(clip: PoseClip, n: int) -> list[Pose]`.
  - `render_pose(pose: Pose, size: int) -> Image` (RGB, fond noir, membres OpenPose COCO avec couleurs standard,
    épaisseur `max(2, size // 64)`).
  - `OPENPOSE_LIMBS: list[tuple[int, int]]`, `OPENPOSE_COLORS: list[tuple[int, int, int]]`.

Algorithme de `sample` (non déterminé par la signature) :

```
t_i = i / n            si clip.loop      (la dernière keyframe boucle vers la première à t = 1)
t_i = i / (n - 1)      sinon
pour t_i : keyframes encadrantes (a, b), u = (t_i - a.t) / (b.t - a.t)
point = lerp(a.p, b.p, u)  si a.p et b.p présents, sinon None
```

- [ ] **Step 1 : tests qui échouent**

```python
def test_grid_shape():
    assert grid_shape(6) == (3, 2) and grid_shape(4) == (2, 2) and grid_shape(16) == (4, 4) and grid_shape(2) == (2, 1)

def test_compose_split_roundtrip():
    imgs = [Image.new("RGB", (40, 40), (i * 30, 0, 0)) for i in range(6)]
    back = split_grid(compose_grid(imgs, 64), 6)
    assert len(back) == 6 and back[5].getpixel((32, 32))[0] == 150

def test_sample_loop_excludes_endpoint():
    clip = PoseClip(loop=True, keyframes=[kf(0.0, x=0.0), kf(0.5, x=1.0)])
    xs = [p.points[0][0] for p in sample(clip, 4)]
    assert xs == pytest.approx([0.0, 0.5, 1.0, 0.5])

def test_sample_no_loop_includes_endpoint():
    clip = PoseClip(loop=False, keyframes=[kf(0.0, x=0.0), kf(1.0, x=1.0)])
    assert [p.points[0][0] for p in sample(clip, 3)] == pytest.approx([0.0, 0.5, 1.0])

def test_sample_missing_point_stays_missing():
    clip = PoseClip(loop=False, keyframes=[kf(0.0, x=0.0), kf(1.0, x=None)])
    assert sample(clip, 3)[1].points[0] is None

def test_render_pose_draws_on_black():
    img = render_pose(standing_pose(), 256)
    assert img.size == (256, 256) and img.getpixel((0, 0)) == (0, 0, 0)
    assert img.getbbox() is not None
```

(`kf` et `standing_pose` sont des helpers de test : 18 points, seul le point 0 varie.)

- [ ] **Step 2 :** `pytest tests/test_grid.py tests/poses -v` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** → PASS.
- [ ] **Step 5 :** commit `feat(poses): grilles, interpolation et rendu des squelettes`.

---

### Task 5: Bibliothèque de poses top-down 4 directions

**Files:**
- Create: `poses/library.py`, `poses/data/topdown4/{idle,walk,attack_unarmed,attack_sword,attack_spear,attack_bow}/{down,left,right,up}.json`,
  `poses/data/topdown4/neutral/{down,left,right,up}.json`, `backend/tools/preview_poses.py`
- Modify: `backend/pyproject.toml` (inclure `poses/data/**/*.json` et `generation/workflows/*.json` dans le paquet)
- Test: `backend/tests/poses/test_library.py`

**Interfaces:**
- Consumes : `PoseClip`, `Pose`, `sample`, `render_pose`, `compose_grid` (Task 4) ; `ViewKind`, `AnimationType`, `Direction` (Task 2).
- Produces : `load_clip(view: ViewKind, anim: AnimationType, direction: Direction) -> PoseClip`,
  `load_neutral(view: ViewKind, direction: Direction) -> Pose`, `list_clips(view) -> list[tuple[AnimationType, Direction]]`
  (lecture via `importlib.resources`).

Contenu des données (décisions d'animation, l'implémenteur règle les coordonnées) :
- Repère : caméra top-down « 3/4 » façon RPG, personnage debout, tête vers le haut de l'image, pieds vers y≈0.92.
- `left` et `right` sont des miroirs exacts l'un de l'autre (`x → 1 - x`, échange des points gauche/droite COCO) :
  écrire `right` à la main, générer `left` par `tools/preview_poses.py --mirror` puis committer le JSON.
- `up` : vue de dos (nez absent, `points[0] = None`, yeux et oreilles absents).
- idle : 2 keyframes (respiration : épaules/tête descendent de 0.01), `loop: true`.
- walk : 4 keyframes (contact, passage, contact opposé, passage), `loop: true`, bras opposés aux jambes.
- attaques : `loop: false`, 3 keyframes (préparation t=0, frappe t≈0.45, retour t=1). Épée : arc horizontal du poignet
  porteur ; lance : poignet porteur projeté vers l'avant dans l'axe de la direction ; arc : bras avant tendu, bras
  arrière tiré à la frappe puis relâché ; mains nues : coup de poing direct.
- `tools/preview_poses.py <anim> [--frames N] [--mirror right]` : écrit dans `data/pose_previews/` une grille des 4 directions
  pour vérifier visuellement.

- [ ] **Step 1 : tests qui échouent**

```python
@pytest.mark.parametrize("anim", list(AnimationType))
@pytest.mark.parametrize("d", list(Direction))
def test_clip_valid(anim, d):
    clip = load_clip(ViewKind.topdown4, anim, d)
    assert clip.keyframes[0].t == 0.0
    assert all(len(k.points) == 18 for k in clip.keyframes)
    assert all(0 <= c <= 1 for k in clip.keyframes for p in k.points if p for c in p)
    assert clip.loop == (anim in (AnimationType.idle, AnimationType.walk))

def test_left_is_mirror_of_right(): ...   # pour chaque anim, points left == miroir(points right) à 1e-6 près

def test_up_has_no_face():
    assert load_clip(ViewKind.topdown4, AnimationType.idle, Direction.up).keyframes[0].points[0] is None

def test_neutral_all_directions():
    assert all(len(load_neutral(ViewKind.topdown4, d).points) == 18 for d in Direction)
```

- [ ] **Step 2 :** `pytest tests/poses/test_library.py -v` → FAIL.
- [ ] **Step 3 :** écrire `library.py`, l'outil de prévisualisation, puis les 28 fichiers JSON.
- [ ] **Step 4 :** `pytest tests/poses -v` → PASS ; lancer `python tools/preview_poses.py walk --frames 6` et vérifier
  à l'œil que les squelettes ressemblent à une marche dans les 4 directions.
- [ ] **Step 5 :** commit `feat(poses): bibliothèque top-down 4 directions`.

---

### Task 6: Étapes du pipeline pixel art

**Files:**
- Create: `pixelart/__init__.py`, `pixelart/steps.py`
- Test: `backend/tests/pixelart/test_steps.py`

**Interfaces:**
- Produces (toutes les fonctions sont pures et prennent / renvoient des `Image` RGBA) :
  - `remove_background_colorkey(img: Image, tolerance: int = 24) -> Image` : couleur de fond = médiane des 4 coins ;
    pixels à distance RGB ≤ tolerance → alpha 0. Si l'image a déjà de la transparence (alpha min < 255), elle est renvoyée telle quelle.
  - `common_bbox(frames: list[Image], alpha_min: int = 1) -> tuple[int, int, int, int] | None` (union des bbox ; `None` si tout est vide).
  - `fit_to_cell(frame: Image, bbox, size: int, anchor: tuple[int, int]) -> Image` : rogne à `bbox`, échelle
    `s = min((size - 2) / bw, anchor_y / bh)`, réduit avec `Image.BOX` puis place le bas-centre de la bbox sur `anchor`.
    Toutes les frames d'une animation utilisent la même bbox, donc la même échelle et le même décalage.
  - `threshold_alpha(img: Image, threshold: int) -> Image` (alpha → 0 ou 255).
  - `add_outline(img: Image, color: tuple[int, int, int]) -> Image` (4-voisinage, uniquement sur les pixels transparents
    adjacents à un pixel opaque).

- [ ] **Step 1 : tests qui échouent**

```python
def test_colorkey_removes_flat_background():
    img = solid((100, 100), (255, 255, 255)); draw_rect(img, (40, 40, 60, 60), (200, 0, 0))
    out = remove_background_colorkey(img)
    assert out.getpixel((0, 0))[3] == 0 and out.getpixel((50, 50))[3] == 255

def test_colorkey_keeps_existing_alpha(): ...   # entrée déjà transparente → identique

def test_common_bbox_union():
    assert common_bbox([rect_frame((10, 10, 20, 20)), rect_frame((30, 5, 40, 15))]) == (10, 5, 40, 20)

def test_common_bbox_all_empty():
    assert common_bbox([Image.new("RGBA", (50, 50))]) is None

def test_fit_to_cell_anchors_feet():
    out = fit_to_cell(rect_frame((10, 0, 30, 80), canvas=(100, 100)), (10, 0, 30, 80), 64, (32, 60))
    assert out.size == (64, 64)
    bb = out.getbbox(); assert bb[3] == 60 and abs((bb[0] + bb[2]) / 2 - 32) <= 1

def test_threshold_alpha_binary(): ...          # valeurs d'alpha ⊂ {0, 255}

def test_outline_only_on_transparent_neighbours():
    out = add_outline(single_pixel_image((5, 5), size=11), (0, 0, 0))
    assert out.getpixel((5, 4))[:3] == (0, 0, 0) and out.getpixel((4, 4))[3] == 0
```

- [ ] **Step 2 :** `pytest tests/pixelart/test_steps.py -v` → FAIL.
- [ ] **Step 3 :** implémenter avec numpy.
- [ ] **Step 4 :** → PASS.
- [ ] **Step 5 :** commit `feat(pixelart): étapes unitaires du pipeline`.

---

### Task 7: Palettes et pipeline complet

**Files:**
- Create: `pixelart/palettes.py`, `pixelart/pipeline.py`
- Test: `backend/tests/pixelart/test_palettes.py`, `backend/tests/pixelart/test_pipeline.py`

**Interfaces:**
- Consumes : étapes de la Task 6 ; `PixelSettings`, `Direction` (Task 2).
- Produces :
  - `RGB = tuple[int, int, int]` ; `PRESET_PALETTES: dict[str, list[RGB]]` avec les clés `pico8` (16 couleurs),
    `db32` (32), `endesga32` (32), valeurs officielles.
  - `parse_palette(text: str) -> list[RGB]` : accepte `.hex` (une couleur par ligne, `#` facultatif) et `.gpl` GIMP ;
    lève `ValueError` si moins de 2 couleurs.
  - `kmeans_palette(pixels: np.ndarray, k: int, seed: int = 0, max_iter: int = 20) -> list[RGB]` (numpy pur ; si moins
    de pixels distincts que `k`, renvoie les couleurs distinctes).
  - `quantize(img: Image, palette: list[RGB]) -> Image` (couleur la plus proche en RGB, alpha conservé, pas de tramage).
  - `character_palette(frames: list[Image], settings: PixelSettings) -> list[RGB]` : `auto` → k-means sur les pixels opaques
    de **toutes** les frames (échantillon max 200 000 pixels, seed 0) ; `preset` / `custom` → la palette correspondante.
  - `process_animation(frames: dict[Direction, list[Image]], settings: PixelSettings, size: int, anchor: tuple[int, int], palette: list[RGB]) -> dict[Direction, list[Image]]`
    : ordre : colorkey → `common_bbox` sur toutes les directions → `fit_to_cell` → `threshold_alpha` → `quantize` → outline (si activé).
    Avec une bbox `None`, renvoie des frames transparentes de `size`×`size`.

- [ ] **Step 1 : tests qui échouent**

```python
def test_presets_sizes():
    assert len(PRESET_PALETTES["pico8"]) == 16 and len(PRESET_PALETTES["db32"]) == 32

def test_parse_hex_and_gpl():
    assert parse_palette("ff0000\n#00ff00\n") == [(255, 0, 0), (0, 255, 0)]
    assert parse_palette("GIMP Palette\nName: x\n#\n255 0 0 red\n0 0 255 blue\n") == [(255, 0, 0), (0, 0, 255)]

def test_kmeans_finds_two_clusters():
    pal = kmeans_palette(two_color_pixels((250, 0, 0), (0, 0, 250)), 2)
    assert sorted(pal) == [(0, 0, 250), (250, 0, 0)]

def test_process_output_shape_and_palette():
    out = process_animation(fake_frames(dirs=4, n=6), PixelSettings(), 64, (32, 60), [(0, 0, 0), (255, 0, 0)])
    assert list(out) == list(DIRECTION_ORDER) and all(len(v) == 6 for v in out.values())
    colors = {px[:3] for f in out[Direction.down] for px in f.getdata() if px[3] == 255}
    assert colors <= {(0, 0, 0), (255, 0, 0)}

def test_process_shared_bbox_no_jitter():
    out = process_animation(frames_with_moving_arm(), PixelSettings(), 64, (32, 60), PRESET_PALETTES["pico8"])
    assert len({f.getbbox()[3] for f in out[Direction.down]}) == 1   # pieds stables

def test_process_animation_with_empty_frame():
    out = process_animation({Direction.down: [Image.new("RGBA", (200, 200))]}, PixelSettings(), 32, (16, 30), [(0, 0, 0), (9, 9, 9)])
    assert out[Direction.down][0].getbbox() is None
```

- [ ] **Step 2 :** `pytest tests/pixelart -v` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** → PASS.
- [ ] **Step 5 :** commit `feat(pixelart): palettes et pipeline`.

---

### Task 8: Export PNG + JSON et script Godot

**Files:**
- Create: `export/__init__.py`, `export/sheet.py`, `export/json_atlas.py`, `export/godot/load_spriteframes.gd`
- Test: `backend/tests/export/test_sheet.py`, `backend/tests/export/test_json_atlas.py`, `backend/tests/export/test_godot.py`

**Interfaces:**
- Consumes : `Project`, `AnimationConfig`, `DIRECTION_ORDER` (Task 2).
- Produces :
  - `ProcessedAnimation = dict[Direction, list[Image]]`.
  - `build_sheet(frames: ProcessedAnimation, size: int, padding: int = 0) -> Image` : ligne r = `DIRECTION_ORDER[r]`,
    largeur = max des longueurs × (size + padding) − padding.
  - `build_animation_json(anim: AnimationConfig, frames: ProcessedAnimation, size: int, padding: int, anchor: tuple[int, int], image_name: str) -> dict`
    : structure exacte de la spec §8 (`frames`, `meta.image`, `meta.size`, `meta.frameTags` avec index globaux
    dans l'ordre d'insertion des frames, `meta.x_autosprite`), `duration = round(1000 / fps)`,
    `frameTags[].direction = "forward"`.
  - `build_character_json(project: Project, animations: list[AnimationConfig]) -> dict` :
    `{name, view, frame_size, anchor: {x, y}, directions: [...], animations: [{name, image, data, fps, loop, frame_count}]}`.
  - `ExportIncomplete(Exception)` avec `missing: list[str]` (ex. `["walk_up"]`).
  - `JsonAtlasExporter.export(project: Project, processed: dict[str, ProcessedAnimation], out: Path) -> Path` : écrit le ZIP
    (`<slug du nom>/…` + `godot/load_spriteframes.gd`) ; ne prend que les animations dont **toutes** les directions sont
    `ready`, sinon lève `ExportIncomplete` ; exige au moins une animation.
  - `load_spriteframes.gd` : `static func build(json_path: String) -> SpriteFrames` ; une animation par `frameTag`,
    `AtlasTexture` par frame sur la texture `meta.image` voisine, vitesse = `x_autosprite.fps`, boucle = `x_autosprite.loop`.

- [ ] **Step 1 : tests qui échouent**

```python
def test_sheet_dimensions_and_rows():
    sheet = build_sheet(colored_frames(per_dir=6, size=64), 64)
    assert sheet.size == (384, 256)
    assert sheet.getpixel((10, 64 + 10)) == COLOR[Direction.left]

def test_sheet_uneven_rows():
    frames = colored_frames(per_dir=6, size=32); frames[Direction.up] = frames[Direction.up][:4]
    data = build_animation_json(anim("walk", fps=10), frames, 32, 0, (16, 30), "walk.png")
    assert build_sheet(frames, 32).size == (192, 128)
    up = next(t for t in data["meta"]["frameTags"] if t["name"] == "walk_up")
    assert (up["from"], up["to"]) == (18, 21)

def test_json_fields():
    data = build_animation_json(anim("attack_sword", fps=12, loop=False), colored_frames(6, 64), 64, 0, (32, 60), "attack_sword.png")
    assert data["frames"]["attack_sword_down_0"] == {"frame": {"x": 0, "y": 0, "w": 64, "h": 64}, "duration": 83}
    assert data["meta"]["x_autosprite"]["rows"] == ["down", "left", "right", "up"]
    assert data["meta"]["x_autosprite"]["loop"] is False

def test_export_zip_layout(tmp_path):
    path = JsonAtlasExporter().export(project_with_ready("walk"), {"walk": colored_frames(6, 64)}, tmp_path / "x.zip")
    names = set(zipfile.ZipFile(path).namelist())
    assert {"chevalier/walk.png", "chevalier/walk.json", "chevalier/character.json", "chevalier/godot/load_spriteframes.gd"} <= names

def test_export_rejects_incomplete(tmp_path):
    with pytest.raises(ExportIncomplete) as e:
        JsonAtlasExporter().export(project_with_stale("walk", Direction.up), {...}, tmp_path / "x.zip")
    assert e.value.missing == ["walk_up"]

@pytest.mark.godot
def test_godot_loader(tmp_path): ...   # GODOT_BIN requis ; lance tests/godot/run_loader.gd en headless, vérifie la sortie "animations=4"
```

- [ ] **Step 2 :** `pytest tests/export -v` → FAIL.
- [ ] **Step 3 :** implémenter, plus `tests/godot/run_loader.gd` (charge un export, imprime `animations=<n>`).
- [ ] **Step 4 :** `pytest tests/export -v` → PASS ; si Godot est installé : `GODOT_BIN=... pytest -m godot` → PASS.
- [ ] **Step 5 :** commit `feat(export): sheets PNG + JSON et chargeur Godot`.

---

### Task 9: Client ComfyUI, workflows et diagnostic

**Files:**
- Create: `comfy/__init__.py`, `comfy/client.py`, `comfy/fake.py`, `comfy/workflows.py`, `comfy/health.py`,
  `generation/workflows/{txt2img,remove_bg,turnaround,pose_grid,pose_inpaint}.json`
- Test: `backend/tests/comfy/test_workflows.py`, `backend/tests/comfy/test_client.py`, `backend/tests/comfy/test_health.py`

**Interfaces:**
- Consumes : `Settings` (Task 1).
- Produces :
  - `ComfyError(Exception)` avec `kind: Literal["unreachable","oom","execution","interrupted"]`, `message: str`.
  - `ComfyClient` (Protocol) : `async upload_image(img: Image, name: str) -> str` (nom côté serveur),
    `async run(workflow: dict, on_progress: Callable[[float], None]) -> list[Image]` (images de tous les nœuds `SaveImage`
    dans l'ordre des ids), `async interrupt() -> None`, `async object_info() -> dict`, `async models(folder: str) -> list[str]`.
  - `HttpComfyClient(base_url: str, client_id: str | None = None)` : `POST /prompt` (`{"prompt": wf, "client_id": id}`),
    WebSocket `/ws?clientId=` (messages `progress` → `value/max`, `executing` avec `node is None` → fin,
    `execution_error` → `ComfyError`, `oom` si `exception_type` ou message contient « OutOfMemory » / « out of memory »),
    `GET /history/{prompt_id}` puis `GET /view?filename=&subfolder=&type=`, `POST /upload/image`, `POST /interrupt`,
    `GET /object_info`, `GET /models/{folder}`. Erreur httpx de connexion → `ComfyError("unreachable")`.
  - `FakeComfyClient(responder: Callable[[dict], list[Image]])` : enregistre `workflows: list[dict]`, `uploads: dict[str, Image]`,
    `interrupted: bool` ; `object_info` renvoie un dict configurable.
  - Workflows : format API de ComfyUI. Les entrées paramétrables sont des nœuds dont `_meta.title` vaut
    `IN:<param>:<input_field>` (ex. `IN:seed:seed` sur le KSampler, `IN:pose_image:image` sur un `LoadImage`).
    Paramètres utilisés : `checkpoint, lora, lora_strength, controlnet, ipadapter_preset, positive, negative, seed, width,
    height, batch, reference_image, pose_image, source_image, mask_image`.
  - `load_workflow(name: str) -> dict`, `bind(workflow: dict, values: dict[str, Any]) -> dict` (copie profonde ;
    `MissingBinding` si un paramètre `IN:` n'a pas de valeur ou si une valeur ne correspond à aucun nœud),
    `params(workflow) -> set[str]`, `required_nodes(workflow) -> set[str]` (les `class_type`).
  - `HealthReport(comfy_reachable: bool, missing_nodes: list[str], missing_models: list[str])` avec la propriété `ok`.
  - `async check_comfy(client: ComfyClient, settings: Settings) -> HealthReport` : nœuds requis par l'ensemble des workflows
    ⊂ clés de `object_info()` ; `checkpoints ∋ settings.checkpoint`, `loras ∋ settings.lora`,
    `controlnet ∋ settings.controlnet_openpose`.

Contenu des workflows (graphe, nœuds standard sauf indication) :
- `txt2img` : CheckpointLoaderSimple → LoraLoader → CLIPTextEncode ×2 → EmptyLatentImage(`width,height,batch`) → KSampler → VAEDecode → SaveImage.
- `remove_bg` : LoadImage(`source_image`) → `RMBG` (ComfyUI-RMBG, modèle RMBG-2.0) → SaveImage.
- `turnaround` et `pose_grid` : comme `txt2img` avec IPAdapterUnifiedLoader(`ipadapter_preset`) + IPAdapterAdvanced
  sur LoadImage(`reference_image`), et ControlNetLoader(`controlnet`) + ControlNetApplyAdvanced sur LoadImage(`pose_image`) ;
  fond uni demandé dans le prompt positif (le service ajoute « plain flat light gray background »).
- `pose_inpaint` : `pose_grid` + LoadImage(`source_image`) + LoadImageMask(`mask_image`) → InpaintModelConditioning → KSampler(denoise 1.0).

- [ ] **Step 1 : tests qui échouent**

```python
@pytest.mark.parametrize("name", ["txt2img", "remove_bg", "turnaround", "pose_grid", "pose_inpaint"])
def test_workflows_load_and_bind(name):
    wf = load_workflow(name)
    bound = bind(wf, {p: sample_value(p) for p in params(wf)})
    assert not any(str(v).startswith("IN:") for n in bound.values() for v in n["inputs"].values())

def test_bind_sets_field():
    wf = load_workflow("txt2img"); out = bind(wf, {**defaults(wf), "seed": 42})
    ks = next(n for n in out.values() if n["_meta"]["title"] == "IN:seed:seed")
    assert ks["inputs"]["seed"] == 42 and wf != out

def test_bind_missing_raises():
    with pytest.raises(MissingBinding): bind(load_workflow("txt2img"), {})

async def test_http_client_unreachable():
    with pytest.raises(ComfyError) as e: await HttpComfyClient("http://127.0.0.1:9").object_info()
    assert e.value.kind == "unreachable"

async def test_http_client_run_flow(): ...   # httpx.MockTransport + faux serveur WS (websockets.serve sur un port libre) :
                                             # progress 1/2 puis 2/2 → on_progress reçoit [0.5, 1.0] ; image renvoyée par /view

async def test_oom_mapped(): ...             # message execution_error contenant "CUDA out of memory" → kind == "oom"

async def test_health_reports_missing():
    fake = FakeComfyClient(lambda wf: [], object_info={"KSampler": {}}, models={"checkpoints": []})
    r = await check_comfy(fake, Settings())
    assert not r.ok and "IPAdapterAdvanced" in r.missing_nodes and Settings().checkpoint in r.missing_models
```

- [ ] **Step 2 :** `pytest tests/comfy -v` → FAIL.
- [ ] **Step 3 :** implémenter le client, le faux client, `bind`, le diagnostic ; écrire les 5 workflows (les construire dans
  ComfyUI puis « Export (API) », renommer les titres en `IN:…`).
- [ ] **Step 4 :** → PASS.
- [ ] **Step 5 :** commit `feat(comfy): client, workflows paramétrés et diagnostic`.

---

### Task 10: Générateurs (référence, vues, animations)

**Files:**
- Create: `generation/__init__.py`, `generation/base.py`, `generation/reference.py`, `generation/pose_generator.py`
- Test: `backend/tests/generation/test_reference.py`, `backend/tests/generation/test_pose_generator.py`

**Interfaces:**
- Consumes : `ComfyClient`, `ComfyError`, `load_workflow`, `bind` (Task 9) ; `grid_shape`, `cell_size`, `compose_grid`,
  `split_grid`, `cell_box` (Task 4) ; `render_pose`, `load_neutral` (Tasks 4–5) ; `Settings`, `Direction`, `ViewKind`.
- Produces :
  - `ProgressCallback = Callable[[float], None]`.
  - `GenerationError(Exception)` : `code: str`, `message: str`, `hint: str | None` ; `from_comfy(e: ComfyError) -> GenerationError`
    (`oom` → code `gpu_oom`, hint « Réduisez le nombre de frames, ou passez à un modèle SD 1.5 dans .env » ;
    `unreachable` → `comfy_unreachable`, hint « Lancez ComfyUI (run_nvidia_gpu.bat) puis réessayez »).
  - `ReferenceGenerator` (Protocol, spec §3) et `ComfyReferenceGenerator(client, settings)` :
    `from_prompt(prompt, n=4, seed)` → `txt2img` avec 1024×1024 et `batch = n` ; `remove_background(img)` → `remove_bg` ;
    `turnaround(reference, view, seed) -> dict[Direction, Image]` → `turnaround` avec une grille 2×2 de poses neutres
    dans l'ordre `DIRECTION_ORDER`, découpée par `split_grid`.
  - `AnimationGenerator` (Protocol, spec §3) et `PoseGenerator(client, settings)` :
    `generate(ref, poses, style_prompt, seed, progress) -> list[Image]` : grille de poses (`cell_size(len(poses), settings.grid_canvas)`),
    largeur et hauteur = cols × cell et rows × cell, workflow `pose_grid`, découpage en `len(poses)` frames ;
    `regenerate_frame(ref, poses, frames, index, style_prompt, seed, progress) -> Image` : grille source = `compose_grid(frames)`,
    masque blanc sur `cell_box(index)` et noir ailleurs, workflow `pose_inpaint`, renvoie la case `index`.
  - Le prompt négatif commun est une constante : `NEGATIVE_PROMPT = "blurry, text, watermark, multiple characters per cell, cropped, background scenery"`.
  - Toute `ComfyError` est convertie en `GenerationError`.

- [ ] **Step 1 : tests qui échouent** (avec `FakeComfyClient`)

```python
async def test_generate_uses_grid_and_splits():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(6, cell=336)])
    frames = await PoseGenerator(fake, Settings()).generate(ref(), poses(6), "pixel art", 7, lambda p: None)
    assert len(frames) == 6 and frames[4].getpixel((5, 5))[:3] == CELL_COLORS[4]
    wf = fake.workflows[0]
    assert input_of(wf, "seed") == 7 and (input_of(wf, "width"), input_of(wf, "height")) == (1008, 672)
    assert fake.uploads[input_of(wf, "pose_image")].size == (1008, 672)

async def test_regenerate_frame_mask_targets_cell():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(6, cell=336)])
    out = await PoseGenerator(fake, Settings()).regenerate_frame(ref(), poses(6), frames(6), 2, "p", 1, lambda p: None)
    mask = fake.uploads[input_of(fake.workflows[0], "mask_image")]
    assert mask.getpixel((2 * 336 + 10, 10)) in (255, (255, 255, 255)) and mask.getpixel((10, 10)) in (0, (0, 0, 0))
    assert out.getpixel((5, 5))[:3] == CELL_COLORS[2]

async def test_turnaround_returns_four_directions(): ...   # dict ordonné down, left, right, up

async def test_oom_becomes_generation_error():
    def boom(wf): raise ComfyError("oom", "CUDA out of memory")
    with pytest.raises(GenerationError) as e:
        await PoseGenerator(FakeComfyClient(boom), Settings()).generate(ref(), poses(4), "p", 0, lambda p: None)
    assert e.value.code == "gpu_oom" and e.value.hint
```

(`cell_size(6, 1024)` vaut 336 : 1024 // 3 = 341, arrondi au multiple de 8 inférieur.)

- [ ] **Step 2 :** `pytest tests/generation -v` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** → PASS.
- [ ] **Step 5 :** commit `feat(generation): générateurs de référence et d'animation guidés par poses`.

---

### Task 11: File de jobs et bus d'événements

**Files:**
- Create: `jobs/__init__.py`, `jobs/events.py`, `jobs/queue.py`
- Test: `backend/tests/jobs/test_queue.py`, `backend/tests/jobs/test_events.py`

**Interfaces:**
- Consumes : `GenerationError` (Task 10), `Storage` (Task 3).
- Produces :
  - `EventBus` : `publish(event: dict) -> None`, `subscribe() -> AsyncIterator[dict]` (une `asyncio.Queue` par abonné,
    taille max 1000, les plus anciens sont écartés si la file est pleine).
  - `JobStatus(StrEnum)` : `queued, running, succeeded, failed, cancelled`.
  - `Job` (Pydantic) : `id, kind: str, project_id: str, target: str, status, progress: float, error: dict | None, created_at, finished_at`.
    `target` identifie la ressource visée (ex. `walk/down`, `walk/down/3`, `views`, `reference`).
  - `JobContext` : `progress(value: float)` (publie `{"type": "job", "job": ...}`), `on_cancel(cb: Callable[[], Awaitable[None]])`.
  - `JobQueue(storage: Storage, events: EventBus)` : `submit(kind, project_id, target, fn: Callable[[JobContext], Awaitable[None]]) -> Job`
    (`JobConflict` si un job `queued`/`running` du même projet a une cible qui est l'autre ou commence par `<autre>/`) ;
    `async cancel(job_id)` ; `get(job_id)` ; `list(project_id: str | None = None)` ; `async start()` ; `async stop()` ;
    `recover()` (appelé par `start` : les jobs `running` ou `queued` persistés passent en `failed` avec le code `interrupted`).
    Jobs persistés dans `jobs.json` (via `Storage`), 200 derniers conservés.
  - Exécution : un worker unique ; `GenerationError` → `failed` avec `{code, message, hint}` ; autre exception →
    `failed` avec `{code: "internal", message: str(e)}` ; annulation → appel des callbacks `on_cancel` (interruption ComfyUI),
    annulation de la tâche asyncio, statut `cancelled`.

- [ ] **Step 1 : tests qui échouent**

```python
async def test_runs_sequentially(queue):
    order = []
    async def fn(name): order.append(name + "+"); await asyncio.sleep(0.01); order.append(name + "-")
    queue.submit("t", "p", "a", lambda c: fn("a")); queue.submit("t", "p", "b", lambda c: fn("b"))
    await wait_idle(queue)
    assert order == ["a+", "a-", "b+", "b-"]

async def test_conflict_on_overlapping_target(queue):
    queue.submit("t", "p", "walk/down", slow)
    with pytest.raises(JobConflict): queue.submit("t", "p", "walk/down/3", slow)
    queue.submit("t", "p", "walk/up", slow)          # pas de conflit

async def test_generation_error_recorded(queue): ...     # error == {"code": "gpu_oom", "message": ..., "hint": ...}

async def test_cancel_running_calls_hook(queue):
    called = asyncio.Event()
    async def fn(ctx): ctx.on_cancel(lambda: _set(called)); await asyncio.sleep(10)
    job = queue.submit("t", "p", "x", fn); await until_running(queue, job.id)
    await queue.cancel(job.id)
    assert called.is_set() and queue.get(job.id).status == JobStatus.cancelled

async def test_recover_marks_interrupted(tmp_path):
    write_jobs_json(tmp_path, status="running"); q = JobQueue(LocalStorage(tmp_path), EventBus()); q.recover()
    assert q.list()[0].status == JobStatus.failed and q.list()[0].error["code"] == "interrupted"

async def test_progress_published(queue, bus): ...      # l'abonné reçoit un événement job avec progress == 0.5
```

- [ ] **Step 2 :** `pytest tests/jobs -v` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** → PASS.
- [ ] **Step 5 :** commit `feat(jobs): file de jobs GPU et bus d'événements`.

---

### Task 12: Service d'orchestration des projets

**Files:**
- Create: `services/__init__.py`, `services/images.py`, `services/projects.py`
- Test: `backend/tests/services/test_images.py`, `backend/tests/services/test_projects.py`

**Interfaces:**
- Consumes : tout ce qui précède.
- Produces :
  - `normalize_upload(data: bytes) -> Image` : ouvre (`ValueError("unsupported_image")` si Pillow échoue), applique
    `ImageOps.exif_transpose`, convertit en RGBA, réduit à 1024 px de côté max (LANCZOS), pose sur un canevas carré
    transparent centré ; taille max des données 20 Mo (`ValueError("image_too_large")`).
  - `ProjectService(repo, storage, ref_gen: ReferenceGenerator, anim_gen: AnimationGenerator, jobs: JobQueue, settings)` :
    - `create_project(name, output_size=64, style_prompt=None) -> Project`, `update_project(pid, patch: ProjectPatch) -> Project`
      (`ProjectPatch` : `name, style_prompt, output_size, pixel_settings, mirror_right` facultatifs ; un changement de
      `output_size` ou de `pixel_settings` relance `reprocess(pid)`).
    - `upload_reference(pid, data: bytes) -> Project` : normalise, stocke `reference_input`, puis lance le job `remove_bg`
      (cible `reference`) qui écrit `candidate(pid, 0)` et passe `reference.status` à `candidates`.
    - `generate_reference(pid, prompt: str, n: int = 4) -> Job` : écrit les candidats `0..n-1` (avec détourage).
    - `select_reference(pid, index: int) -> Project` : copie le candidat vers `reference_image`, statut `validated`.
    - `generate_views(pid, direction: Direction | None = None) -> Job` (cible `views` ou `views/<dir>`) : exige une référence
      validée ; sans `direction`, appelle `ref_gen.turnaround` ; avec `direction`, appelle `anim_gen.regenerate_frame` sur
      la grille 2×2 des vues actuelles (poses neutres, index = position dans `DIRECTION_ORDER`) ;
      si `mirror_right`, `right` = miroir horizontal de `left`.
    - `validate_view(pid, d) -> Project`.
    - `configure_animations(pid, configs: list[AnimationConfigIn]) -> Project` (`AnimationConfigIn` : `type`, `frame_count`, `fps` ;
      ajoute ou met à jour ; un `frame_count` différent sur une direction `ready` la passe en `stale`).
    - `generate_animation(pid, anim_id, directions: list[Direction] | None = None) -> list[Job]` : un job par direction
      (cible `<anim>/<dir>`) ; exige la vue de la direction en statut `generated` ou `validated` ;
      poses = `sample(load_clip(...), frame_count)` ; écrit `raw/000.png…`, `frames` = noms, statut `ready`, puis `reprocess`.
    - `regenerate_frame(pid, anim_id, d, index) -> Job` (cible `<anim>/<dir>/<index>`).
    - `set_frames(pid, anim_id, d, frames: list[str]) -> Project` : sous-ensemble ordonné des frames existantes
      (`ValueError` sinon, liste non vide).
    - `import_frame(pid, anim_id, d, index, data: bytes) -> Project` : remplace le fichier brut (via `normalize_upload`).
    - `reprocess(pid, anim_id: str | None = None) -> None` : palette du personnage (`character_palette` sur toutes les frames
      brutes) puis `process_animation`, écriture dans `processed/`.
    - `preview(pid, anim_id, d) -> PreviewOut(fps: int, loop: bool, frames: list[str])` (clés de stockage des frames traitées).
    - `export(pid) -> str` (clé du ZIP ; laisse remonter `ExportIncomplete`).
  - Avant chaque job GPU, `check_comfy` est appelé ; si le rapport n'est pas `ok`, le job échoue avec
    `GenerationError("comfy_not_ready", ..., hint=<nœuds et modèles manquants>)` sans appeler ComfyUI.
  - Chaque job publie `{"type": "project", "project": <Project>}` sur le bus après chaque modification.
  - Un job qui échoue remet le statut de la direction à sa valeur précédente (`empty` ou `ready`).

- [ ] **Step 1 : tests qui échouent** (`FakeComfyClient` + vrais générateurs, ou faux générateurs qui renvoient des
  rectangles colorés sur fond gris)

```python
def test_upload_normalizes_odd_images():
    for data in [jpeg_bytes((3000, 1200)), png_bytes(mode="P"), png_bytes(mode="LA"), png_with_alpha()]:
        img = normalize_upload(data); assert img.mode == "RGBA" and img.size[0] == img.size[1] <= 1024
    with pytest.raises(ValueError, match="unsupported_image"): normalize_upload(b"not an image")

async def test_full_flow_to_export(svc):
    p = svc.create_project("Chevalier")
    await run(svc.generate_reference(p.id, "knight")); svc.select_reference(p.id, 0)
    await run(svc.generate_views(p.id))
    svc.configure_animations(p.id, [AnimationConfigIn(type="walk", frame_count=6, fps=10)])
    for j in svc.generate_animation(p.id, "walk"): await run(j)
    assert svc.preview(p.id, "walk", Direction.up).frames and zip_has(svc.export(p.id), "chevalier/walk.png")

async def test_frame_count_change_marks_stale(svc_with_walk):
    p = svc_with_walk.configure_animations(pid, [AnimationConfigIn(type="walk", frame_count=8, fps=10)])
    assert p.animation("walk").directions[Direction.down].status == "stale"
    assert len(svc_with_walk.preview(pid, "walk", Direction.down).frames) == 6
    with pytest.raises(ExportIncomplete): svc_with_walk.export(pid)

async def test_conflicting_job_rejected(svc_with_walk):
    svc_with_walk.generate_animation(pid, "walk", [Direction.down])
    with pytest.raises(JobConflict): svc_with_walk.regenerate_frame(pid, "walk", Direction.down, 2)

async def test_views_require_validated_reference(svc): ...      # ValueError("reference_not_validated")
async def test_mirror_right(svc): ...                            # right == ImageOps.mirror(left)
async def test_set_frames_rejects_unknown(svc_with_walk): ...
async def test_settings_change_reprocesses(svc_with_walk): ...   # output_size 32 → frames traitées en 32×32
async def test_failed_job_restores_status(svc_failing): ...      # statut redevient "empty"
async def test_job_fails_when_comfy_not_ready(svc_missing_models): ...  # error.code == "comfy_not_ready", aucun workflow envoyé
```

- [ ] **Step 2 :** `pytest tests/services -v` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** → PASS ; `pytest` complet → PASS.
- [ ] **Step 5 :** commit `feat(services): orchestration des projets`.

---

### Task 13: API REST, WebSocket et fichiers

**Files:**
- Create: `api/__init__.py`, `api/app.py`, `api/errors.py`, `api/deps.py`, `api/routes/{health,projects,reference,views,animations,jobs,files,export,ws}.py`,
  `backend/src/pixelforge/__main__.py` (`python -m pixelforge` → uvicorn sur 127.0.0.1:8000)
- Test: `backend/tests/api/test_api.py`, `backend/tests/api/test_errors.py`

**Interfaces:**
- Consumes : `ProjectService` (Task 12), `JobQueue`, `EventBus` (Task 11), `check_comfy` (Task 9).
- Produces :
  - `create_app(settings: Settings | None = None, comfy: ComfyClient | None = None) -> FastAPI` (démarre et arrête le worker
    dans `lifespan`, CORS configuré via `settings.cors_origins`).
  - Les routes de la spec §9, toutes préfixées par `/api`, plus `GET /api/files/{key:path}` (sert un fichier de `DATA_DIR`,
    uniquement sous `projects/`) et `GET /api/presets/palettes` (noms et couleurs des presets).
    Les routes qui lancent un job renvoient `202` avec le `Job` (ou la liste des jobs).
  - Correspondance des erreurs (`api/errors.py`, format des contraintes globales) :
    `ProjectNotFound` → 404 `not_found` ; `JobConflict` → 409 `conflict` ; `ExportIncomplete` → 409 `export_incomplete`
    (message qui liste `missing`) ; `ValueError(code)` → 400 avec `code` ; `ValidationError` de FastAPI → 422 `invalid_request` ;
    `GenerationError` → 502 avec son code et son hint ; autre exception → 500 `internal`.
  - `WS /api/ws` : relaie chaque événement du bus en JSON.
  - `GET /api/health` → `{"backend": "ok", "comfy": HealthReport}` (ne lève jamais d'erreur).

- [ ] **Step 1 : tests qui échouent** (`TestClient(create_app(Settings(data_dir=tmp_path), FakeComfyClient(...)))`)

```python
def test_create_and_get_project(client):
    r = client.post("/api/projects", json={"name": "Chevalier"}); assert r.status_code == 201
    assert client.get(f"/api/projects/{r.json()['id']}").json()["output_size"] == 64

def test_not_found_format(client):
    assert client.get("/api/projects/nope").json() == {"error": {"code": "not_found", "message": ANY, "hint": None}}

def test_invalid_output_size(client):
    assert client.post("/api/projects", json={"name": "x", "output_size": 4}).json()["error"]["code"] == "invalid_request"

def test_generate_returns_202_and_ws_progress(client): ...   # with client.websocket_connect("/api/ws") : reçoit un événement "job"
def test_files_route_blocks_escape(client): ...              # /api/files/../../etc → 400 ou 404, jamais 200
def test_export_incomplete_409(client): ...
def test_health_when_comfy_down(client_down): ...            # 200, comfy.comfy_reachable == False
```

- [ ] **Step 2 :** `pytest tests/api -v` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** → PASS ; `python -m pixelforge` démarre et `curl http://127.0.0.1:8000/api/health` renvoie du JSON.
- [ ] **Step 5 :** commit `feat(api): routes REST, WebSocket et fichiers`.

---

### Task 14: Socle frontend (client API, événements, bandeau, jobs)

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts` (proxy `/api` et `/api/ws` vers `127.0.0.1:8000`),
  `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`,
  `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/hooks/useEvents.ts`,
  `frontend/src/components/StatusBanner.tsx`, `frontend/src/components/JobsPanel.tsx`, `frontend/src/styles.css`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes : l'API de la Task 13.
- Produces :
  - `types.ts` : `Direction`, `AnimationType`, `Project`, `AnimationConfig`, `DirectionState`, `PixelSettings`, `Job`,
    `HealthResponse`, `ApiErrorBody`, alignés sur les modèles Pydantic (mêmes noms de champs, en snake_case).
  - `class ApiError extends Error { code: string; hint: string | null; status: number }`.
  - `api` : un objet avec une fonction par route (`listProjects, createProject, getProject, updateProject, uploadReference,
    generateReference, selectReference, generateViews, validateView, configureAnimations, generateAnimation,
    regenerateFrame, setFrames, importFrame, preview, exportProject, listJobs, cancelJob, health, palettePresets`) ;
    `fileUrl(key: string): string`.
  - `useEvents(onEvent: (e: ServerEvent) => void)` : WebSocket avec reconnexion (délai 1 s puis doublé, max 10 s).
  - Dépendances : react, react-dom, react-router-dom ; dev : vite, @vitejs/plugin-react, typescript, vitest.
  - `App.tsx` : routes `/`, `/p/:id/reference`, `/p/:id/views`, `/p/:id/animations`, `/p/:id/review`, `/p/:id/export`
    (pages provisoires jusqu'aux tâches 15–16) ; `StatusBanner` (interroge `health` toutes les 10 s, affiche les nœuds et
    modèles manquants) ; `JobsPanel` (liste des jobs en direct, bouton d'annulation, message et hint des erreurs).

- [ ] **Step 1 : test qui échoue**

```ts
test("api error is parsed", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "conflict", message: "busy", hint: null } }), { status: 409 }));
  await expect(api.getProject("x")).rejects.toMatchObject({ code: "conflict", status: 409 });
});
```

- [ ] **Step 2 :** `cd frontend && npm install && npx vitest run` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** `npx vitest run` → PASS ; `npx tsc --noEmit` et `npm run build` → OK.
- [ ] **Step 5 :** commit `feat(frontend): socle, client API et suivi des jobs`.

---

### Task 15: Écrans projets, référence et vues

**Files:**
- Create: `frontend/src/pages/ProjectsPage.tsx`, `frontend/src/pages/ReferencePage.tsx`, `frontend/src/pages/ViewsPage.tsx`,
  `frontend/src/hooks/useProject.ts`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/hooks/useProject.test.ts`

**Interfaces:**
- Consumes : `api`, `useEvents`, `types` (Task 14).
- Produces : `useProject(id: string): { project: Project | null; reload(): Promise<void> }`, mis à jour par les événements
  `{"type": "project"}` dont `project.id === id`.

Comportement des écrans :
- **Projets** : liste avec vignette de référence, formulaire de création (nom, taille 16–256 par défaut 64, style),
  suppression avec confirmation.
- **Référence** : deux onglets, *Importer* (zone de dépôt PNG/JPG) et *Décrire* (prompt + nombre de propositions 1–4) ;
  grille des candidats ; bouton « Utiliser celle-ci » → `selectReference` ; lien vers les vues quand le statut est `validated`.
- **Vues** : 4 cases dans l'ordre `down, left, right, up`, chacune avec régénération et validation ; case « right = miroir de
  left » ; bouton « Générer les 4 vues ». Le bouton qui mène aux animations est actif dès que les 4 vues sont `generated`
  ou `validated`.
- Les images s'affichent avec `image-rendering: pixelated` et un paramètre de cache (`?v=<horodatage de l'événement>`).

- [ ] **Step 1 : test qui échoue**

```ts
test("useProject applies matching project events only", () => { /* événement sur un autre id ignoré, sur le bon id appliqué */ });
```

- [ ] **Step 2 :** `npx vitest run` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** `npx vitest run` → PASS ; `npm run build` → OK ; vérification manuelle avec le backend et `FakeComfyClient`
  (variable `PIXELFORGE_FAKE_COMFY=1` lue par `__main__.py` pour démarrer sans GPU) : créer un projet, générer la référence, les vues.
- [ ] **Step 5 :** commit `feat(frontend): écrans projets, référence et vues`.

(Le mode `PIXELFORGE_FAKE_COMFY=1` est ajouté à `config.py` et `__main__.py` dans cette tâche : `fake_comfy: bool = False` ;
le faux client renvoie des rectangles colorés sur fond gris, aux tailles demandées par le workflow.)

---

### Task 16: Écrans animations, revue et export

**Files:**
- Create: `frontend/src/lib/playback.ts`, `frontend/src/lib/review.ts`, `frontend/src/components/SpritePlayer.tsx`,
  `frontend/src/pages/AnimationsPage.tsx`, `frontend/src/pages/ReviewPage.tsx`, `frontend/src/pages/ExportPage.tsx`,
  `frontend/src/components/PixelSettingsPanel.tsx`
- Test: `frontend/src/lib/playback.test.ts`, `frontend/src/lib/review.test.ts`

**Interfaces:**
- Consumes : `api`, `useProject`, `types`.
- Produces :
  - `frameAt(elapsedMs: number, fps: number, count: number, loop: boolean): number` : index = `floor(elapsed * fps / 1000)`,
    modulo `count` si `loop`, sinon borné à `count - 1`.
  - `reorder(frames: string[], from: number, to: number): string[]` et `removeAt(frames: string[], index: number): string[]`
    (refuse de vider la liste : renvoie la liste inchangée).
  - `<SpritePlayer frames={string[]} fps loop scale={1|4} />` : canvas, `imageSmoothingEnabled = false`, `requestAnimationFrame`.

Comportement des écrans :
- **Animations** : une ligne par `AnimationType` (case à cocher, frames 2–16, FPS 1–60, valeurs par défaut des contraintes
  globales) ; « Enregistrer » → `configureAnimations` ; « Générer » par animation ou pour toutes.
- **Revue** : grille animations × directions ; chaque case affiche `SpritePlayer` (×1 et ×4), son statut (`stale` affiché
  « à régénérer »), la bande des frames avec les actions régénérer, supprimer, déplacer (glisser-déposer → `setFrames`) et
  importer (→ `importFrame`) ; panneau `PixelSettingsPanel` (mode de palette, nombre de couleurs, preset, import `.hex`/`.gpl`
  lu côté client puis envoyé en `custom_colors`, contour, couleur, seuil alpha, taille de sortie) appliqué via `updateProject`
  avec un délai de 300 ms.
- **Export** : liste des animations prêtes et manquantes ; bouton « Exporter » → téléchargement du ZIP ; en cas de
  `export_incomplete`, affiche la liste `missing`.

- [ ] **Step 1 : tests qui échouent**

```ts
test("frameAt loops", () => { expect(frameAt(1000, 6, 4, true)).toBe(2); expect(frameAt(0, 6, 4, true)).toBe(0); });
test("frameAt clamps when not looping", () => { expect(frameAt(5000, 12, 6, false)).toBe(5); });
test("reorder moves", () => { expect(reorder(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]); });
test("removeAt keeps last frame", () => { expect(removeAt(["a"], 0)).toEqual(["a"]); });
```

- [ ] **Step 2 :** `npx vitest run` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** `npx vitest run` → PASS ; `npm run build` → OK ; parcours manuel complet avec `PIXELFORGE_FAKE_COMFY=1`
  jusqu'au ZIP, puis ouverture du ZIP dans Godot (si disponible) avec `load_spriteframes.gd`.
- [ ] **Step 5 :** commit `feat(frontend): animations, revue, réglages pixel art et export`.

---

### Task 17: Installation Windows, documentation et test GPU réel

**Files:**
- Create: `docs/setup-comfyui.md`, `.env.example`, `start.bat`, `README.md`, `backend/tests/e2e/test_gpu_flow.py`

**Interfaces:**
- Consumes : tout.

Contenu :
- `docs/setup-comfyui.md` : installation de ComfyUI portable pour Windows ; nœuds personnalisés (via ComfyUI-Manager) :
  `ComfyUI_IPAdapter_plus`, `ComfyUI-RMBG` ; modèles et dossiers de destination :
  `checkpoints/sd_xl_base_1.0.safetensors`, `loras/pixel-art-xl.safetensors` (nerijs/pixel-art-xl),
  `controlnet/controlnet-openpose-sdxl-1.0.safetensors` (xinsir), `ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors`,
  `clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` ; conseils pour 8 Go (lancer ComfyUI avec `--lowvram` en cas
  d'OOM) ; repli SD 1.5 : équivalents à indiquer dans `.env`.
- `.env.example` : toutes les variables `PIXELFORGE_*` de `Settings`, commentées.
- `start.bat` : crée `backend\.venv` si absent, installe le backend, `npm install` si `node_modules` absent, vérifie que
  ComfyUI répond sur `PIXELFORGE_COMFY_URL` (avertissement sinon, sans bloquer), lance `python -m pixelforge` et `npm run dev`
  dans deux fenêtres, ouvre `http://localhost:5173`.
- `README.md` : présentation, prérequis, démarrage rapide, mode `PIXELFORGE_FAKE_COMFY=1`, lancement des tests.
- `test_gpu_flow.py` (`@pytest.mark.gpu`) : avec le vrai ComfyUI, prompt → référence → vues → walk 6 frames → export ;
  vérifie que le ZIP contient `walk.png` en 384×256 pour 64 px.

- [ ] **Step 1 :** écrire le test GPU ; `pytest -m gpu` sans ComfyUI → échec explicite « comfy_unreachable ».
- [ ] **Step 2 :** écrire la documentation, `.env.example`, `start.bat`, `README.md`.
- [ ] **Step 3 :** vérifier : `pytest` (défaut) → PASS ; `npm run build` → OK ; sur la machine Windows de l'utilisateur :
  `start.bat` puis `pytest -m gpu` → PASS (à faire par l'utilisateur, le conteneur n'a pas de GPU).
- [ ] **Step 4 :** commit `docs: installation Windows, ComfyUI et test GPU`.
