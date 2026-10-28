# Installer ComfyUI pour PixelForge (Windows)

PixelForge ne génère rien lui-même : il pilote un **ComfyUI local**. Ce guide installe ComfyUI, les nœuds
personnalisés et les modèles nécessaires (testé sur le papier pour une RTX 4060 8 Go ; voir « Vérifier les
workflows » ci-dessous).

## 1. ComfyUI portable

1. Téléchargez « ComfyUI_windows_portable_nvidia » depuis la page *Releases* de
   <https://github.com/comfyanonymous/ComfyUI> et décompressez-le (7-Zip), par exemple dans `C:\ComfyUI`.
2. Utilisez une version **récente** : les workflows PixelForge emploient les nœuds natifs `PrimitiveInt` et
   `PrimitiveFloat`, absents des anciennes versions. Si le bandeau de santé de PixelForge les signale comme
   manquants, mettez à jour (`update\update_comfyui.bat`).
3. Lancez `run_nvidia_gpu.bat`. ComfyUI doit répondre sur <http://127.0.0.1:8188>.

## 2. Nœuds personnalisés

Installez [ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager) (clonez-le dans
`ComfyUI\custom_nodes`), relancez ComfyUI, puis *Manager → Install Custom Nodes* :

| Nœud personnalisé | Fournit (class_type) |
|---|---|
| `ComfyUI_IPAdapter_plus` | `IPAdapterUnifiedLoader`, `IPAdapterAdvanced` |
| `ComfyUI-RMBG` | `RMBG` (détourage) |

Relancez ComfyUI après l'installation. Les autres nœuds utilisés (`CheckpointLoaderSimple`, `LoraLoader`,
`ControlNetLoader`, `ControlNetApplyAdvanced`, `KSampler`, `InpaintModelConditioning`, `PrimitiveInt`,
`PrimitiveFloat`…) sont natifs.

## 3. Modèles

Chemins relatifs au dossier `ComfyUI\models\` :

| Fichier | Dossier | Source |
|---|---|---|
| `sd_xl_base_1.0.safetensors` | `checkpoints/` | stabilityai/stable-diffusion-xl-base-1.0 (Hugging Face) |
| `pixel-art-xl.safetensors` | `loras/` | nerijs/pixel-art-xl |
| `controlnet-openpose-sdxl-1.0.safetensors` | `controlnet/` | xinsir/controlnet-openpose-sdxl-1.0 (renommer le fichier téléchargé si besoin) |
| `ip-adapter-plus_sdxl_vit-h.safetensors` | `ipadapter/` | h94/IP-Adapter (`sdxl_models/`) |
| `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` | `clip_vision/` | h94/IP-Adapter (`models/image_encoder/`, renommer `model.safetensors`) |

Le modèle de détourage RMBG-2.0 est téléchargé automatiquement par `ComfyUI-RMBG` au premier usage.
L'encodeur d'image **CLIP-ViT-H** (dossier `clip_vision`) est indispensable à l'IP-Adapter : sans lui,
`IPAdapterUnifiedLoader` échoue.

Les noms de fichiers doivent correspondre à ceux de `.env` (`PIXELFORGE_CHECKPOINT`, `PIXELFORGE_LORA`,
`PIXELFORGE_CONTROLNET_OPENPOSE`) ; voir `.env.example`.

## 4. Vérifier les workflows (important)

Les cinq workflows de `backend/src/pixelforge/generation/workflows/` (`txt2img`, `remove_bg`, `turnaround`,
`pose_grid`, `pose_inpaint`) ont été écrits **sans ComfyUI en ligne** : les options du nœud RMBG
(`model`, `background`…) et la chaîne du preset IP-Adapter (`PLUS (high strength)`) peuvent différer selon
les versions des nœuds. À contrôler une fois :

1. Dans ComfyUI : *Workflow → Open* et choisissez chaque fichier `.json` (le format API se charge aussi).
2. Un nœud **rouge** ou une valeur refusée signale une option invalide : corrigez-la dans l'interface
   (liste déroulante).
3. Faites *Workflow → Export (API)* et remplacez le fichier dans `backend/src/pixelforge/generation/workflows/`.
   **Conservez les titres `IN:<paramètre>:<champ>`** des nœuds (ex. `IN:seed:seed`, `IN:checkpoint:ckpt_name`) : c'est ainsi que
   PixelForge injecte ses valeurs. Si vous renommez un nœud, l'application ne le trouvera plus.
4. Si seul le preset IP-Adapter change, modifiez plutôt `PIXELFORGE_IPADAPTER_PRESET` dans `.env`.

Le bandeau de santé de PixelForge (et `GET /api/health`) liste les nœuds et modèles manquants.

## 5. Conseils pour 8 Go de VRAM

- En cas de **mémoire insuffisante (OOM)** : lancez ComfyUI avec `--lowvram`, en ajoutant l'option à la ligne de
  `run_nvidia_gpu.bat` (`...main.py --windows-standalone-build --lowvram`).
- Réduisez `PIXELFORGE_GRID_CANVAS` (768) et le nombre de frames par animation.
- Fermez les applications qui utilisent le GPU (navigateur avec accélération, jeux).
- La première génération est longue (chargement des modèles) ; les suivantes sont plus rapides.

## 6. Repli SD 1.5

Si SDXL est trop lent ou trop gourmand, utilisez des équivalents SD 1.5 et indiquez-les dans `.env` :

```
PIXELFORGE_CHECKPOINT=<checkpoint SD 1.5, ex. v1-5-pruned-emaonly.safetensors>
PIXELFORGE_LORA=<LoRA pixel art SD 1.5>
PIXELFORGE_CONTROLNET_OPENPOSE=control_v11p_sd15_openpose.pth
PIXELFORGE_GRID_CANVAS=768
```

Ajoutez aussi `ip-adapter-plus_sd15.safetensors` dans `models/ipadapter/` (l'encodeur CLIP-ViT-H est le même).
Le preset `PLUS (high strength)` couvre SD 1.5 et SDXL ; les workflows doivent être rouverts dans ComfyUI
(§ 4) pour vérifier la compatibilité avant usage.
