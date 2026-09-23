# Animals, horses and carriages

The first-pass animals were procedural primitive blobs built in `assets/blender/build_assets.py -- --animals`.
They are replaced by third-party models (all CC0 except one CC-BY hawk), rescaled, re-oriented and re-animated
by `assets/blender/build_animals.py`, plus a procedural hire carriage and farm cart built in the same script.

```
bash tools/fetch_animals.sh                          # ~26 MB of sources into assets/third_party/ (git-ignored)
# (the generated fur maps are cached in assets/textures/animals/, also git-ignored)
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
| [OpenGameArt: Simple Cat](https://opengameart.org/content/simple-cat) (Drummyfish) | CC0 | 114-tri cat with a photographic tabby texture made from CC0 Wikimedia photos; two-shape-key walk. Used in the first pass, replaced by the refined cat below (too low-poly next to the MakeHuman people). |
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
| `dog_hound` | Quaternius Wolf, reshaped (ogar polski: drop ears, deep chest, low sabre tail), fur | 0.62 m | idle, walk, run | 12,000 |
| `dog_spitz` | Quaternius Husky, reshaped (wolfspitz: ruff, plume curled over the back), fur | 0.50 m | idle, walk, run | 12,000 |
| `cat` | Quaternius Husky rig reshaped into a cat (flat face, round skull, tabby fur, whiskers) | 0.25 m at the shoulder | idle, walk, sit (keyed here) | 9,060 |
| `pigeon` | mujtaba-io pigeon | 0.30 m long | idle, walk (keyed here), fly | 1,010 |
| `crow` | Teh_Bucket raven | 0.45 m long | idle, fly | 2,380 |
| `hawk` | Sherkiz hawk | 0.55 m long | fly, idle (= fly) | 9,956 |
| `carriage` | procedural dorożka, textured | 1.5 m track, 0.66 m rear wheels | - | 6,136 |
| `horse_cart` | procedural ladder cart, textured | 0.62 m wheels | - | 3,252 |
| `coach` | procedural travelling coach (inn yard), textured; replaces build_assets.py's `coach` | 0.72 m rear wheels | - | 5,692 |
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

## Dogs and cat: second pass (higher fidelity)

A second search for login-free, higher-fidelity CC0 / CC-BY dogs and cats came up empty:
- OpenGameArt 3D "dog" / "hound" / "cat": low-poly or cartoon only ([Benny the Rottweiler](https://opengameart.org/content/benny-the-rottweiler)
  is CC-BY-SA and stylised; [Canine low poly](https://opengameart.org/content/canine-low-poly) is CC-BY, blocky).
- Smithsonian Open Access 3D (CC0): the API returns no dog or cat specimens with 3D media.
- Wikimedia Commons 3D: statue scans (STL) only.
- Quaternius and KayKit: no higher-poly animal packs; everything is stylised low-poly.
- Blend Swap ([rigged, animated cat](https://blendswap.com/blend/18519), CC-BY) needs a login ("Sign in to download").
  itch.io asset listings answer HTTP 403 to scripts. Meshy's "CC0" dogs are AI-generated and need an account.

So the dogs and the cat are **refined procedurally from the Quaternius rigs** (keeping their skinning and clips):
1. weld the flat-shaded split vertices;
2. breed shape by bone-weighted displacement: hound leathers lengthened, thinned and swung down beside the
   cheek, chest deepened behind the elbows, rounder skull, longer muzzle, slim sabre tail carried low; spitz
   ruff and coat inflated, smaller ears, shorter muzzle, plume tail curled over the back; cat face flattened,
   skull rounded, head enlarged, small wide ears, slim body, plumper legs, thin tail carried low then up;
3. tail postures baked into a new rest pose (so the clips keep them);
4. triangles to quads, **Subdivision Surface level 2** applied, decimated back to 12k (dogs) / 9k (cat), smooth shading;
5. smart UV project, the coat colours (black-and-tan, cream, or a procedural mackerel tabby with a pale belly for
   the cat) baked to a 1024 albedo, multiplied by a generated **fur texture** (strand noise) with matching
   **fur normal and roughness maps**;
6. cat: 10 whiskers as tapered strands skinned to the head, and a keyed **sit** clip (haunches down, forelegs
   straight, tail wrapped); a standing cat plays "sit" in the game.

## Caveats
- The dogs and the cat are still built on Quaternius' low-poly bodies: smoother and furred now, with breed
  silhouettes, but not photoreal. A realistic rigged dog or cat would need a Sketchfab / Blend Swap account.
- The cat's tail is short for a cat (bone scaling in the rest pose broke the clips' translation keys, so only
  rotations are baked); its legs are pale because the tabby blends to cream below the flank.
- The hawk has only a flight clip and is modelled wings-spread, so it can only fly (hawks are not night birds;
  it is there because the falconer lost it).
- Vehicles use build_assets.py's baked oak / iron / glass / cloth / thatch / snow textures (imported through
  importlib, tinted per key) with its auto_uv(). The dorożka has a lacquered body with a red coach line,
  crimson cushions, a leather hood on iron hoops, leaf springs, iron-tyred wheels, mudguards, steps, lamps,
  whip, pole, splinter bar and swingletrees; the cart a plank bed, ladder sides, sacks and hay, iron-shod wheels,
  shafts to the horse's shoulders; the coach a swelled green body, glazed doors with half-drawn blinds, gilt
  mouldings and a coat-of-arms roundel, C-springs with leather braces, roof rail, strapped trunks under snow,
  hammercloth box, lamps, steps, pole.
- `coach.glb` is written by both build scripts: build_assets.py's DRESSING `coach()` still exists (not edited),
  so a full `build_assets.py` run overwrites the new one; run `build_animals.py` afterwards.
- `build_assets.py -- --animals` overwrites `horse.glb`, `cat.glb` and `pigeon.glb`; rerun `build_animals.py`.
