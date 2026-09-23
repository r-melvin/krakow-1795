# Animals, horses and carriages

The first-pass animals were procedural primitive blobs built in `assets/blender/build_assets.py -- --animals`.
They are replaced by third-party models (all CC0 except one CC-BY hawk), rescaled, re-oriented and re-animated
by `assets/blender/build_animals.py`, plus a procedural hire carriage and farm cart built in the same script.

```
bash tools/fetch_animals.sh                          # ~26 MB of sources into assets/third_party/ (git-ignored)
blender -b --python assets/blender/build_animals.py  # writes assets/models/<name>.glb (~4 MB in total)
blender -b --python assets/blender/render_animals.py -- --out /tmp/animals   # lineup renders to check them
```

Run `build_animals.py` **after** `build_assets.py -- --animals` if you run both: the old builders still write
`horse.glb`, `cat.glb` and `pigeon.glb` under the same names.

## Research (September 2026)

What we needed: a horse above all, dogs of breeds plausible in 1795 Kraków (hound, spitz, mastiff type), a cat,
pigeons, crows and a hawk; CC0 or CC-BY so a public MIT / CC-BY project can ship them; glTF, FBX or .blend;
rigged with idle and walk clips if possible; closer to realistic than cartoon, to sit next to the MakeHuman
people.

### Blender add-ons
| Option | Finding |
|---|---|
| Animal generators ("Sapling for animals", MakeHuman for quadrupeds) | None exist. MPFB/MakeHuman is humans only. |
| Auto-Rig Pro, Rigify quadruped metarigs | Rigging only (Auto-Rig Pro is paid); no meshes. Rigify's horse/wolf metarigs are bones only. |
| BlenderKit (now "Blendkit") | Search API is public (`/api/v1/search/?query=horse+asset_type:model+is_free:true`), downloads need an account API key via the add-on. The good free horses and carriages ("Draft horse", "Simple Old Horse-Drawn Carriage", Prussian wagons) are **Royalty Free**, which forbids redistributing the model files: unusable in a public repo. Filtering `license:cc_zero` returns no usable animals (a horse statue, a horse head, a "funny pigeon sculpture"). Rejected. |

### Downloadable model sources
| Source | Licence | Findings |
|---|---|---|
| [OpenGameArt: Rigged Horse](https://opengameart.org/content/rigged-horse) (Lyndon Daniels' model from the [Realtime Rancher's pack](https://opengameart.org/content/realtime-ranchers-3d-model-pack), rigged by ChadM) | CC0 | **Realistic** draught horse, 7.4k tris body plus mane and tail cards, 2k diffuse / normal / AO and hair textures packed in the .blend. 19-bone rig, **no animation**. The best horse found by a wide margin. **Used.** |
| [Quaternius Ultimate Animated Animal Pack](https://quaternius.com/packs/ultimateanimatedanimals.html), mirrored per model on [Poly Pizza](https://poly.pizza/bundle/Animated-Animal-Pack-ILAPXeUYiS) (direct `static.poly.pizza/<id>.glb` downloads, no login) | CC0 | Horse, White Horse, Donkey, Husky, Shiba Inu, Wolf, Fox, deer, cattle, alpaca; ~1.9k tris each, flat colours, 12+ clips (Idle, Walk, Gallop, Eating...). Stylised low-poly. The **Wolf and Husky are used** for the hound and spitz: nothing better with a rig and clips was obtainable. The Quaternius horse was the fallback. |
| [Quaternius Farm Animal Pack](https://poly.pizza/bundle/Farm-Animal-Pack-1kUvRTPLzT) | CC0 | Horse, cow, pig, sheep, pug, llama, zebra with clips; cartoon proportions. Not used. |
| Quaternius cats and pigeon on Poly Pizza ([Cat](https://poly.pizza/m/qKICY6xla2), [Pigeon](https://poly.pizza/m/9NGlBTpDEr)) | CC0 | Animated but chibi (huge heads and eyes). Rejected as too cartoon. |
| [OpenGameArt: Simple Cat](https://opengameart.org/content/simple-cat) (Drummyfish) | CC0 | 114-tri cat with a photographic tabby texture made from CC0 Wikimedia photos; two-shape-key walk. Reads as a real cat at game distance. **Used.** |
| [OpenGameArt: Low poly pigeon, rigged + animated](https://opengameart.org/content/low-poly-3d-pigeon-model-rigged-animated-untextured) (mujtaba-io) | CC0 | 1k tris, 13-bone rig, flap and glide clips, untextured, modelled in flight. **Used** (ground pose, walk and colours added). |
| [OpenGameArt: Raven](https://opengameart.org/content/raven-0) (Teh_Bucket) | CC0 | ~1.2k tris (mirrored), textured, rigged, stand and fly clips. **Used** as the crow. |
| [Poly Pizza: Hawk Lp Rigged](https://poly.pizza/m/RkN6MEbP6g) (Sherkiz) | CC-BY 3.0 | 10k tris, textured, rigged, Fly clip. **Used** (credit required, see README). |
| [OpenGameArt: Yellow-billed shrike](https://opengameart.org/content/bird-yellow-billed-shrike) | CC0 | Nicely textured songbird, IK rig, no clips. Wrong species; a candidate for small birds later. |
| [OpenGameArt: 3D wolf animation for game](https://opengameart.org/content/3d-wolf-animation-for-game), [Dog low poly rigged](https://opengameart.org/content/dog-low-poly-rigged) | CC0 | Crude wolf with clips; untextured faceted Jack Russell without clips. Not better than Quaternius. |
| [OpenGameArt: horse drawn carriage](https://opengameart.org/content/horse-drawn-carriage) (Lotnik) | CC0 | Actually a Polish ladder wagon ("wóz"), box primitives, textures missing from the .blend. Not used; the cart is procedural. |
| Poly Pizza "Poly by Google" animals (beagle, crow, hawks, cats) | CC-BY 3.0 | Static (no rig), ~500-700 tris, faceted. Not used. |
| Kenney | CC0 | No realistic animals. |
| Poly Haven | CC0 | No animals (a horse statue and head only). |
| Sketchfab CC0 / CC-BY | varies | Many good rigged horses and dogs, but downloads need a logged-in account / API token. Skipped per brief. |
| Blend Swap | CC0 / CC-BY | Downloads need a login. Skipped. |
| Wikimedia Commons 3D | varies | STL scans of statues only. |
| Horse-drawn carriages anywhere | - | No CC0/CC-BY fiacre, droshky or coach found outside Royalty-Free BlenderKit and login-only Sketchfab. Built procedurally. |

## What ships

| glb | Source | Scale | Clips | Tris |
|---|---|---|---|---|
| `horse` | Daniels/ChadM horse | 1.60 m at the withers | idle, walk (keyed here) | 14,986 |
| `horse_harnessed` | same + procedural harness | 1.60 m | idle, walk | 16,478 |
| `dog_hound` | Quaternius Wolf, recoloured black-and-tan (ogar polski) | 0.62 m | idle, walk, run | 1,962 |
| `dog_spitz` | Quaternius Husky, recoloured cream (wolfspitz) | 0.50 m | idle, walk, run | 1,920 |
| `cat` | Drummyfish cat | 0.25 m at the shoulder | idle, walk (shape keys) | 114 |
| `pigeon` | mujtaba-io pigeon | 0.30 m long | idle, walk (keyed here), fly | 1,010 |
| `crow` | Teh_Bucket raven | 0.45 m long | idle, fly | 2,380 |
| `hawk` | Sherkiz hawk | 0.55 m long | fly, idle (= fly) | 9,956 |
| `carriage` | procedural dorożka | 1.5 m track, 0.66 m rear wheels | - | 3,436 |
| `horse_cart` | procedural ladder cart | 0.62 m wheels | - | 1,800 |
| `hitch_rail` | procedural | 2.7 m rail | - | 196 |

Conventions (the same as `build_assets.py`): front at Blender -Y (Godot +Z), origin on the ground under the body,
NLA tracks named like the humans' clips, a `<name>-colonly` box, textures embedded as WebP (Godot 4 imports
`EXT_texture_webp`; the horse's mane keeps its alpha). Vehicles carry empties the runtime reads:
`horse_slot_N` (where a `horse_harnessed` stands; its traces end 1.95 m behind its centre, at the splinter bar),
`driver_seat`, `lamp_L`/`lamp_R`, and `wheel_*` objects with their origin on the hub.

Build notes:
- The horse's walk is a 4-beat gait keyed per leg chain (32 frames at 30 fps, ~1.5 m/s at speed 1), with a head
  nod twice per stride and a tail swing; idle breathes, flicks ears and tail and rests a hind leg.
- The harness is fitted to the mesh: collar, hames, back pad with terrets and girth, traces, bridle with
  blinkers and bit, reins over the neck to the driver. Pieces are skinned to the neck, head or spine bone.
- The pigeon was modelled flying; its ground pose folds the wings along the flanks, and its walk bobs the head.
- The .blend sources predate node materials; the script rebuilds Principled materials from their packed images.

## In the city

`scripts/npc/animal.gd` plays the rigged clips ("walk" scaled to ground speed, "idle" when stopped) and adds:
- **`drive`** (`kind: "vehicle"` in `data/npcs.json`): the harnessed team is the body; the vehicle rides on a
  top-level CharacterBody3D dragged behind on its pole, so it tracks the team through corners like a real
  trailer. Wheels spin with distance, the coachman (`town_coachman` if built) sits posed on the box, a lamp
  glows. It stops for the player, townsfolk, guards and other vehicles in front of the horses (and edges past a
  townsman who has stood in the road for 12 s). Both bodies carry NavigationObstacle3Ds so walkers steer round.
- **`circle`**: flies a loop at the post height (the hawk over the square).
- **`tether`**: a hitching rail in front of a standing horse's head.

Roster (`data/npcs.json`): the **dorożka** (2 horses, 2.0 m/s) and a **peasant cart** (1 horse, 1.4 m/s) drive the
`road_*` post loop: in along the north side of the square past St Mary's, out through the north-west corner,
round the outside of the west, south and east rows, and back in through the gap between St Mary's and the east
row. A saddle horse stands tethered by St Adalbert's (27, 19); three pigeons pick about by the Cloth Hall; two
crows; the hawk circles 24 m up; the falconer's dog is now the hound and the lapdog the spitz.

## Caveats
- The dogs are Quaternius low-poly, flat-shaded and stylised; they are the weakest link. A realistic rigged dog
  would need a Sketchfab account (many CC-BY ones) or a commission.
- The cat is only 114 triangles (photo-textured card-like limbs); fine at a distance, poor close up.
- The hawk has only a flight clip and is modelled wings-spread, so it can only fly (hawks are not night birds;
  it is there because the falconer lost it).
- The carriage and cart are procedural and plain-shaded (no baked wood textures yet).
- `build_assets.py -- --animals` overwrites `horse.glb`, `cat.glb` and `pigeon.glb`; rerun `build_animals.py`.
