# Unreal Engine spike plan: agent-driven, headless, on Linux

Decision-grade research for porting *Kraków 1795* from Godot 4.7 to Unreal Engine, keeping the current
discipline: text-first authoring, headless smoke tests, scripted screenshots, one GPU lock, Claude Code agents doing
the work. Research date: **2026-09-24**. Every claim carries a source; anything marked **[unverified]** could not be
confirmed from a primary source and must be checked on the machine during the spike.

**Headline.** Do not target 5.6. Target **UE 5.8.3** (hotfix released 2026-09-22): it is the last UE5 release before
UE6, it is the only version with Epic's own in-editor MCP server (which is what Epic's official Claude Code plugin
talks to), MetaHuman Creator runs on Linux from 5.7, Chaos Cloth is production-ready, and the 5.7 SDL3/Wayland
breakage and 5.8.0 Linux Vulkan crashes are fixed in the hotfixes. 5.6 has none of that and its Linux launch was
rough (5.6.0 RADV crash fixed only in 5.6.1).

---

## 0. Summary table

| Question | Answer | Confidence |
|---|---|---|
| Which version | 5.8.3 prebuilt Linux binaries; source build only if we adopt the Angelscript fork | High |
| Install cost | ~25 GB zip, ~43 GB unpacked (prebuilt); ~225 GB and several hours (source) | Medium (sizes from 5.3/5.7 reports) |
| GPU/driver | NVIDIA 570+ required (5.6+); Vulkan SM6 needs `VK_EXT_mesh_shader`; 16 GB VRAM is fine | High |
| Live Coding on Linux | No. Hot Reload exists but is flaky; plan on editor restart per C++ change | High |
| Edit-compile-see loop (C++) | ~30 s to 3 min per change vs 2 s in Godot | Medium [unverified on this box] |
| Headless smoke | `UnrealEditor-Cmd ... -nullrhi -ExecCmds="Automation RunTests X" -TestExit=...`; exit code is always 0, parse `index.json` | High |
| Headless screenshots | `-game -RenderOffscreen` + `HighResShot` or Movie Render Queue; needs the GPU (our lock) | High |
| Agent tooling | Epic's official `unreal-engine-skills-for-claude-code` plugin + UE 5.8 `ModelContextProtocol` plugin; Linux supported | High |
| Text scripting with hot reload | Hazelight Angelscript fork (source build, Epic GitHub org needed); UnrealSharp has no Linux yet | Medium |
| Licence | 5% royalty over $1M lifetime gross per product; 3.5% via Launch Everywhere; MetaHuman under the same EULA | High |
| Hard blockers | None found. Soft blockers: iteration speed, binary assets, RAM headroom with Blender in parallel | - |

---

## 1. Getting UE on Linux

### 1.1 Prebuilt vs source

| | Prebuilt binaries | Source build |
|---|---|---|
| Access | Epic account; download zip from unrealengine.com/linux | GitHub account linked to EpicGames org (free) |
| Size | ~25 GB zip, ~43 GB unpacked (5.3 report); "20-30 GB" (2026 report) | ~225 GB total per 2026 report; one 5.6 guide says plan 500 GB |
| Time | unzip | `Setup.sh` (downloads ~20+ GB deps), `GenerateProjectFiles.sh`, `make` — "hours"; on 32 cores/30 GB RAM expect 1.5-4 h for `UnrealEditor` **[unverified]** |
| Plugins | Binary plugins work | Must build all plugins from source |
| Needed for | Everything in this plan except Angelscript | Angelscript fork; engine patches |
| CachyOS | AUR `unreal-engine-bin` tracks Epic zips (5.6.1 → 5.7.x seen); glibc 2.28+ is trivially satisfied | |

Sources: Linux quickstart (dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-quickstart-for-unreal-engine);
requirements (…/linux-development-requirements-for-unreal-engine); building from source
(…/building-unreal-engine-from-source); babaei.net 5.6 Linux source guide (2025-06-08);
somethinglikegames.de/en/blog/2026/linux_06_ue/ (2026); medium.com/@esquivelgor/unreal-engine-on-linux-d9721ad39bb7 (5.3 sizes);
aur.archlinux.org/packages/unreal-engine-bin.

RAM: Epic recommends 32 GB; source compile "with less than 32 GB, don't even try" (2026 report). We have 30 GB, so
source builds need a swapfile and `-j` capped (the AngelBeach Makefile uses `nproc-2` and a 32 GB swapfile).

### 1.2 Version status on Linux (checked 2026-09-24)

| Version | Date | Linux notes |
|---|---|---|
| 5.6.0 / 5.6.1 | 2025-06 / 2025-08 | Requires NVIDIA 570+ and `VK_EXT_mesh_shader` for SM6; 5.6.0 crashed on RADV (fixed 5.6.1); Fab/Bridge DNS bug on systemd-resolved hosts; UBA enabled by default caused 10x slower builds for some (`bAllowUBAExecutor=false` fixes) |
| 5.7.0 / 5.7.1 | 2025-11-12 | SDL3 upgrade: Wayland menus centred, tooltips steal focus; use `SDL_VIDEODRIVER=x11`; MetaHuman Creator plugin now on Linux; Nanite skeletal mesh Beta |
| 5.8.0 | 2026-06-17 | Instant `VK_ERROR_DEVICE_LOST` on Linux for some NVIDIA/RADV users (reports from CachyOS, Arch, Nobara); Epic merged fixes to dev-5.8 |
| 5.8.1 / 5.8.2 / 5.8.3 | 2026-07-28 / ? / 2026-09-22 | 5.8.1 "260 fixes" (Vulkan fixes expected here, not itemised **[unverified]**); 5.8.3 fixes a Linux-only Sequencer crash; "Wayland works ok with minor issues on latest 5.8" |
| UE6 | EA "late 2027" | Verse + Scene Graph; 5.8 is the last UE5 |

Sources: forums.unrealengine.com/t/unreal-engine-5-6-startup-vulkan-error-and-vk-ext-mesh-shader/2332700;
…/t/unreal-5-6-on-linux-start-and-crash/2540599; …/t/build-time-increased-10x-when-migrating-from-5-5-to-5-6/2571374;
…/t/ue-5-8-release-instant-vulkan-crash-vk-error-device-lost-on-linux-with-rtx-3090-ti-nvidia-driver/2729632;
…/t/5-8-1-hotfix-released/2738864; …/t/5-8-3-hotfix-released/2833315; github.com/AchetaGames/Epic-Asset-Manager/issues/334;
dev.epicgames.com/documentation/unreal-engine/updating-unreal-engine-on-linux-to-sdl3; unrealengine.com/news/the-road-to-ue-6.

### 1.3 Vulkan and NVIDIA

- Requirements page (5.7-5.8): NVIDIA **570+**, RADV 25.0+, clang 20.1.8 toolchain, "GeForce 2080 / 8 GB+" recommended.
- Community: 555/560/565 had issues; 570/575+ confirmed working June 2025. CachyOS ships current `nvidia` packages, so this is fine; pin the driver once it works.
- Vulkan RHI is VRAM-hungry compared with D3D12; 16 GB is comfortable.
- Fallback if SM6 fails: `DefaultGraphicsRHI=SF_VULKAN_SM5` in `[/Script/LinuxTargetPlatform.LinuxTargetSettings]` (loses Nanite/Lumen HW features, so only for triage).
- Known Linux crash class: OpenSSL ABI mismatch with licensed Vulkan drivers (Epic tech note RxpX) **[details unverified; page did not render]**.

### 1.4 Build speed on Linux

- **Live Coding is Windows-only** (Epic docs). Linux has Hot Reload, which Epic's own community wiki says to avoid; users report needing an editor restart anyway.
- **UBA** (Unreal Build Accelerator): C++ compilation on Linux "stable" since 5.5, local cache executor; shader compile via UBA broken in 5.6, fixed 5.7 (Epic docs). If builds are inexplicably slow, set `<bAllowUBAExecutor>false</bAllowUBAExecutor>` in `~/.config/Unreal Engine/UnrealBuildTool/BuildConfiguration.xml`.
- **ccache**: no native UBT support (long-standing request); UBA's local cache is the supported equivalent.
- Unity builds and adaptive unity are on by default; leave them. `bUseUBTMakefiles` gives fast outdatedness checks.
- Useful flags: `Build.sh <Target>Editor Linux Development -Project=… -NoHotReloadFromIDE -Progress`; `-NoLiveCoding` on the editor command line.
- Measured data points (Windows, i9-13900K): clean build of an 8-module plugin 90-104 s; incremental single-file changes are typically 10-40 s compile + link, then 20-120 s editor relaunch (DDC warm) **[Linux numbers unverified; measure on day 1]**.

Sources: dev.epicgames.com/documentation/unreal-engine/using-live-coding-to-recompile-unreal-engine-applications-at-runtime;
unrealcommunity.wiki/live-compiling-in-unreal-projects-tp14jcgs; forums.unrealengine.com/t/ue5-live-coding-hot-reload-on-linux/645512;
dev.epicgames.com/documentation/unreal-engine/build-configuration-for-unreal-engine;
dev.epicgames.com/documentation/unreal-engine/horde-unreal-build-accelerator-and-remote-compilation-tutorial-for-unreal-engine;
forums.unrealengine.com/t/how-to-use-ccache-for-c-compilation-for-faster-compile-times/335274.

---

## 2. Headless / CLI

All of these are documented cross-platform; on Linux the binary is `Engine/Binaries/Linux/UnrealEditor-Cmd` (or
`UnrealEditor` with the same flags). Flags reference: dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-command-line-arguments-reference.

| Need | Mechanism | Notes |
|---|---|---|
| Run editor Python, no GUI | `UnrealEditor-Cmd P.uproject -run=pythonscript -script=/abs/s.py -nullrhi -unattended -nop4 -stdout -FullStdOutLogOutput` | Fastest path; no level loaded (call `unreal.EditorLoadingAndSavingUtils.load_map` first if needed). Python 3.11.8 bundled. |
| Run Python with full editor init | `-ExecutePythonScript=/abs/s.py` | Loads startup map; editor exits when the script returns (by design). |
| Console commands at start | `-ExecCmds="cmd1; cmd2"` | Works in editor and `-game`. |
| No GPU at all | `-nullrhi` | Authoring, tests, cooking. Screenshots come out black. |
| GPU but no window | `-game -RenderOffscreen -unattended -nosplash` | For `HighResShot` and Movie Render Queue; needs our `with_gpu.sh` lock. |
| Screenshot | `HighResShot 1920x1080 filename=/abs/out.png` via `-ExecCmds` or Python `unreal.AutomationLibrary.take_high_res_screenshot(...)` | Not in Shipping builds. Files land under `Saved/Screenshots/Linux/` unless `filename=` given. |
| Cinematic frames | `-game -MoviePipelineConfig=/Game/Cine/Queue -RenderOffscreen -windowed -resx=1920 -resy=1080 -log` | MRQ; or `-MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelinePythonHostExecutor -ExecutorPythonClass=/Engine/PythonTypes.X` for a Python executor. |
| Tests (our `--smoke`) | `-nullrhi -nosound -unattended -nop4 -ExecCmds="Automation RunTests Krakow" -TestExit="Automation Test Queue Empty" -ReportExportPath=/abs/report -log` | **Exit code is 0 even on failure**; parse `report/index.json`. |
| Gauntlet | `RunUAT.sh RunUnreal -project=… -platform=Linux -configuration=Development -build=editor -test=UE.EditorAutomation -runtest=Krakow` | Heavier; use once packaged tests matter. |
| Cook/package | `RunUAT.sh BuildCookRun -project=/abs/P.uproject -platform=Linux -clientconfig=Development -cook -stage -pak -archive -archivedirectory=/abs/out -unattended -utf8output -nop4` | Add `-build` if code changed; `-nocompileeditor` to skip editor rebuild. |
| Build code | `Engine/Build/BatchFiles/Linux/Build.sh KrakowEditor Linux Development -Project=/abs/P.uproject -Progress` | UBT; fails fast with clear exit code. |
| Log to stdout | `-stdout -FullStdOutLogOutput` (order matters), `-abslog=/abs/run.log` | Grep `Error:`, `Warning:`, `LogAutomationController`, `Fatal error`. |
| Keep one editor up and drive it | (a) Python remote execution: UDP multicast 239.0.0.1:6766 discovery, TCP 127.0.0.1:6776 commands, opt-in under Project Settings > Python > Enable Remote Execution; (b) Remote Control API: HTTP :30010, WS :30020, `-RCWebControlEnable -RCWebInterfaceEnable` in `-game`; (c) UE 5.8 MCP server http://127.0.0.1:8000/mcp | (c) is what the Claude Code plugin uses; (a) is what most third-party MCP servers use. |

Practical exit-code rules: UBT and UAT return non-zero on failure; the editor/commandlet returns 0 unless it
crashes, so every skill below must grep the log or parse JSON.

Sources: dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python;
forums.unrealengine.com/t/prevent-editor-from-exiting-when-running-from-command-line-with-executepythonscript/2108201;
gamedevpensieve.com/engines/unreal/unreal_devops/unreal_testing; github.com/ibbles/LearningUnrealEngine (exit code note);
dev.epicgames.com/documentation/en-us/unreal-engine/running-gauntlet-tests-in-unreal-engine;
dev.epicgames.com/documentation/en-us/unreal-engine/using-command-line-rendering-with-move-render-queue-in-unreal-engine;
dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-for-unreal-engine; pypi.org/project/upyrc;
forums.unrealengine.com/t/outputting-logs-in-unrealeditor-cmd/1538861.

---

## 3. Text-first authoring

### 3.1 What is binary and what to do about it

| Asset | Format | Agent strategy |
|---|---|---|
| `.umap` levels | binary | Turn on **World Partition + One File Per Actor**: each actor becomes its own small `.uasset` under `__ExternalActors__`, so diffs are per-actor and merges rarely conflict. Better: spawn the city from data at load (as now), keep the map nearly empty. |
| Blueprints | binary | Avoid for logic. Use C++ (or Angelscript) classes; use Python only to create thin BP subclasses/data-only BPs. Python can create a Blueprint asset, add components (`SubobjectDataSubsystem`) and set defaults, but **graph nodes are not scriptable from Python**; UE 5.8 MCP `BlueprintTools` can add nodes/pins live in the editor. |
| Materials | binary graphs | Author a few master materials once (by hand or via MCP `MaterialTools`), then create **Material Instances from Python** (`MaterialEditingLibrary`, `AssetTools.create_asset` with `MaterialInstanceConstantFactoryNew`, set scalar/vector/texture params). Optionally write `.usf`/`.ush` custom HLSL files, which are text. |
| DataTables / DataAssets | binary containers | Source of truth stays JSON in `data/`; `unreal.DataTableFunctionLibrary.fill_data_table_from_json_file(dt, path, row_struct)` regenerates them. Row structs are C++ `USTRUCT`s (text). |
| Anim Blueprints | binary graphs | Cannot build graphs from Python. Use C++ `UAnimInstance` with `NativeUpdateAnimation` plus Motion Matching (PoseSearch databases are data assets configurable from Python) or simple montage playback from C++. |
| Meshes/textures/sounds | binary imports | Re-importable from our glTF/PNG/WAV; treat as build outputs, not sources. |
| Config | `Config/*.ini` text | Fully agent-friendly; most engine and plugin settings live here. |
| Text asset export | `.utxt` (JSON) | Editor preference "Text Asset Format Support" (experimental) exports/imports assets as JSON; good for diff/review, not as a source format (format changes between versions). |

### 3.2 Git practice

- `.gitattributes`: `*.uasset filter=lfs diff=lfs merge=lfs -text` and the same for `*.umap`; LFS for `Content/`, plain git for `Source/`, `Config/`, `Script/`, `data/`, Python.
- Ignore `Binaries/ Intermediate/ DerivedDataCache/ Saved/ .vs/ *.sln`.
- OFPA: Epic's changelist UI assumes Perforce, but the on-disk layout works with git; commit from the shell after `-run=pythonscript` saves.
- Diffing: `UnrealEditor-Cmd P.uproject -diff A.uasset B.uasset` opens the Blueprint diff (GUI). For text review use `.utxt` export or the `DiffAssets` commandlet. Community: `atenfyr/UAssetGUI`, `theqoqqi/uasset-diff-tool`.

### 3.3 Scripting languages

| Option | Hot reload | Linux | Status 2026-09 | Verdict |
|---|---|---|---|---|
| C++ | No (restart) | Yes | Core | Default for systems; keep modules small |
| Editor Python 3.11 | n/a (editor-only) | Yes | Core | All pipeline/authoring automation; not gameplay |
| Blueprint | Yes | Yes | Core | Avoid except glue that must be BP (input contexts, tiny wrappers) |
| **Hazelight Angelscript fork** | Yes, incl. non-structural during PIE | Builds on Linux (community Makefile targets `angelscript-master`, pushed 2026-09-22); Hazelight docs only mention Visual Studio | Ships in It Takes Two / Split Fiction; repo is private to EpicGames-org-linked accounts; fork's UE version unverified (repo 404 without org access) | Best fit for "GDScript-like" iteration; costs a source build and locks us out of binary plugins |
| UnrealSharp (C#) | Yes | **Planned, not supported** | UE 5.6-5.8, active (pushed 2026-09-24), MIT | Not on Linux; skip |
| Verse | n/a | n/a | UEFN only; UE6 (EA late 2027) | Not available |
| UE 5.8 MCP `execute_tool_script` | live | Yes | Experimental | Agent-driven live edits, not a language |

Sources: angelscript.hazelight.se (getting-started/installation); github.com/nergnezor/AngelBeach (Makefile); github.com/UnrealSharp/UnrealSharp;
dev.epicgames.com/documentation/en-us/unreal-engine/one-file-per-actor-in-unreal-engine; unrealengine.com/en-US/blog/diffing-unreal-assets;
github.com/elliotttate/unreal-utxt-converter; wikidocs.net/224856 (Blueprint from Python); forums.unrealengine.com/t/how-do-i-use-python-create-anim-node/467902;
dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/DataTableFunctionLibrary.

---

## 4. Pipeline port

| Ours today | Unreal equivalent | Notes / risks |
|---|---|---|
| Blender 5.2 + MPFB headless → glTF | **Interchange** glTF import (`unreal.InterchangeManager.import_asset(...)` with a skeletal-mesh pipeline; morph targets supported) | Open bug UE-392966: Interchange glTF truncates skin weights to 4 influences per vertex (reported 2026-08-20 on 5.8). One community note claims glTF morph targets/animation broken in 5.5/5.6, working from 5.7 **[unverified]**. Fallback: FBX from the same Blender script (legacy FBX importer or Interchange FBX behind `Interchange.FeatureFlags.Import.FBX`). |
| Send to Unreal addon | `EpicGames/BlenderTools` is active (pushed 2026-09-09) but FBX-based and GUI-oriented | Not needed; our exporter + `ue-import` skill is simpler and headless. |
| MPFB clothes as separate skinned meshes | Skeletal mesh + `Chaos Cloth` asset via the Dataflow Cloth Panel Editor (production-ready in 5.8) | Cloth asset authoring from Python is **[unverified]**; day 1 keep clothes skinned, treat cloth sim as a stretch goal. |
| `data/*.json` (27 files) | DataTables (tabular: missions, npcs, factions…) and DataAssets/plain JSON read at runtime via `FJsonObjectConverter` in C++ | Keep JSON as source; either sync to DataTables (`ue-data` skill) or load JSON directly in C++ at startup (zero asset churn; recommended for the spike). |
| `data/city_layout.json` → procedural city | Same, spawned from C++ at load; or a Python generator that writes OFPA actors once | Runtime spawn keeps the map text-driven. |
| Sky/weather (`docs/SKY.md`) | `SkyAtmosphere` + `VolumetricCloud` + `ExponentialHeightFog` (volumetric) + `Lumen` GI/reflections; `MegaLights` production-ready in 5.8 for many lanterns | All settable from C++/Python; Vulkan Lumen SM6 works on NVIDIA 570+. |
| Crowds (street life) | Mass Entity / MassAI crowds (5.8 adds MetaHuman Crowd, experimental) | Mass is still "experimental" in tone; our own C++ crowd on skeletal meshes is simpler at 20-200 people. |
| Animation | Motion Matching (PoseSearch, production-ready since 5.4) or montages from C++ | No AnimBP graphs needed. |
| Nanite for people | Nanite skeletal mesh: experimental 5.5-5.6, Beta 5.7+; `r.Nanite.AllowSkinning=1` | Optional; useful for 100+ crowd only. |
| MetaHuman | MetaHuman Creator in-editor on Linux since 5.7; licence allows use anywhere | Cannot run the MPFB→MetaHuman path automatically; MetaHumans are heavy. Keep MPFB people. |
| numpy SFX | Import WAV; `MetaSounds` for procedural/random variation | Production-ready; graphs are binary but simple presets suffice. |
| UI | UMG is binary; **Slate from C++** is text; CommonUI for gamepad focus | For an agent workflow prefer Slate in C++ (or a thin UMG shell). |

Sources: dev.epicgames.com/documentation/unreal-engine/importing-assets-using-interchange-in-unreal-engine;
forums.unrealengine.com/t/interchange-gltf-importer-truncates-skeletal-mesh-bone-influences-to-4-per-vertex/2745391;
github.com/EpicGames/BlenderTools; dev.epicgames.com/community/learning/tutorials/Wb2V (Chaos Cloth 5.8);
cgchannel.com/2026/06/see-5-key-features-for-cg-artists-in-unreal-engine-5-8/; dev.epicgames.com/documentation/en-us/unreal-engine/motion-matching-in-unreal-engine;
portal.productboard.com/epicgames/1-unreal-engine-public-roadmap/c/2219-nanite-foliage-skinning-experimental-; static.makehumancommunity.org/mpfb/docs/exporting.html.

---

## 5. Agent tooling

### 5.1 MCP servers for Unreal (checked via GitHub API 2026-09-24)

| Server | Transport into UE | Exposes | UE | Linux | Activity | Verdict |
|---|---|---|---|---|---|---|
| **Epic `ModelContextProtocol` plugin (in-engine)** + `EpicGames/unreal-engine-skills-for-claude-code-plugin` | HTTP/SSE 127.0.0.1:8000/mcp inside the editor | 30+ toolsets: actors, Blueprints (nodes/pins), materials, Niagara, Sequencer, DataTables, meshes, tests, **screenshots**, `ProgrammaticToolset.execute_tool_script` (arbitrary Python), Live Coding | **5.8 only**, experimental | Yes (plugin README; proxy binary `Bin/Linux/unreal_mcp_proxy`) | pushed 2026-09-17, MIT, 303 stars | **Use this.** Needs the editor UI running (GPU + display). |
| `chongdashu/unreal-mcp` | C++ plugin TCP 55557 + FastMCP | actors, BP classes/components/nodes, input | 5.5+ | Not stated | pushed 2025-04-22, 2.1k stars, EXPERIMENTAL | Dormant; superseded by Epic |
| `flopperam/unreal-engine-mcp` (now "Aura") | C++ plugin | 64 tools, 46 free | ? | ? | pushed 2026-06-26, 1.1k stars, commercial pivot | Skip |
| `kvick-games/UnrealMCP` | C++ TCP | scene, Python exec | 5.5 | "I only use Windows" | pushed 2025-06-22 | Skip |
| `runreal/unreal-mcp` | Python remote execution | Python-in-editor | any with Python plugin | should work (pure Python) **[unverified]** | pushed 2025-06-06, MIT, 115 stars | Fallback if we stay on <5.8 |
| `sam-david/unreal-mcp` | Py remote exec + Remote Control + optional plugin | 127 tools, screenshots, camera | 5.3+ (tested 5.6) | Not mentioned (Win/Mac paths) | pushed 2026-03-28, 6 stars, beta | Skip |
| `FFZackFair92/unreal-engine-mcp` | Remote Control + Python | no C++ plugin | 5.x | ? | pushed 2026-08-24, 4 stars | Skip |

### 5.2 Claude Code skills and plugins

- **Official:** `/plugin install unreal-engine-skills-for-claude-code@claude-plugins-official`. Contains skills `unreal-mcp` (tool discovery via `list_toolsets`/`describe_toolset`/`call_tool`), `create-toolset` (write our own C++/Python toolsets), `unreal-skill` (author in-project Agent Skills that the editor registers via `AgentSkillToolset`), and a SessionStart hook. Setup: enable `ModelContextProtocol` and `AllToolsets` in the `.uproject`, `bAutoStartServer=True` in `Saved/Config/LinuxEditor/EditorPerProjectUserSettings.ini` (or `-ModelContextProtocolStartServer`), then `ModelContextProtocol.GenerateClientConfig ClaudeCode` writes `.mcp.json`. Security: loopback, no auth, `execute_tool_script` is arbitrary Python; do not run with `--dangerously-skip-permissions` while attached.
- **Community knowledge skills:** `gamedev-skills/awesome-gamedev-agent-skills` (6 Unreal skills: blueprints, C++ gameplay, enhanced input, behavior trees, Niagara, packaging; 1.1k stars, pushed 2026-09-10) and `kevinpbuckley/unreal-engine-skills` (~48 `ue-*` skills incl. `ue-editor-scripting-and-python`, `ue-automation-and-testing`, `ue-importing-content`; pushed 2026-09-09). Both are reference text, not tools; worth installing for vocabulary.
- **Gap the official plugin does not cover:** anything that must run *without* the editor UI. That is exactly our headless discipline, so we write six project skills (drafts in `.claude/skills/`, each with TODOs to fill after install):

| Skill | Wraps | Lock |
|---|---|---|
| `ue-build` | `Build.sh` (UBT) and `RunUAT.sh BuildCookRun` | `with_cpu.sh -n 24` |
| `ue-py` | `UnrealEditor-Cmd -run=pythonscript -nullrhi` and remote execution into a live editor; returns stdout | none / `with_cpu.sh` |
| `ue-import` | Interchange import of a glTF folder with a JSON settings file | `with_cpu.sh` |
| `ue-shot` | `-game -RenderOffscreen` + camera list → PNGs | `with_gpu.sh` |
| `ue-test` | `Automation RunTests` + `index.json` parser, pass/fail exit | `with_cpu.sh` (nullrhi) |
| `ue-data` | `data/*.json` → DataTables (JSON shape conversion + `fill_data_table_from_json_file`) | `with_cpu.sh` |

Sources: github.com/EpicGames/unreal-engine-skills-for-claude-code-plugin (README, skills/unreal-mcp/SKILL.md, references/setup.md);
dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor; github.com/chongdashu/unreal-mcp; github.com/kvick-games/UnrealMCP;
github.com/runreal/unreal-mcp; github.com/sam-david/unreal-mcp; github.com/flopperam/unreal-engine-mcp;
github.com/gamedev-skills/awesome-gamedev-agent-skills; github.com/kevinpbuckley/unreal-engine-skills.

---

## 6. Reality check

### 6.1 Iteration speed per change (estimates for this machine; measure on day 1)

| Loop | Godot today | Unreal on Linux | Notes |
|---|---|---|---|
| Data/JSON change → see it | 2 s launch | 15-40 s (`-run=pythonscript` sync) or 0 s if C++ reads JSON at startup, then a `-game` launch 20-60 s | Read JSON directly in the spike |
| Script change → see it | 2 s | Angelscript: ~1-3 s hot reload; C++: 10-40 s compile + link, then 20-120 s editor/`-game` relaunch | Live Coding not available |
| Headless smoke | ~3-6 s | 20-60 s startup with warm DDC + test time; first run after import compiles shaders for minutes | `-nullrhi` skips most shader work |
| Screenshot set | ~10 s per set | 40-90 s per `-game -RenderOffscreen` run, plus PSO/shader warm-up on first run | Batch all cameras in one process |
| Cold editor start | n/a | 1-3 min first time (shader/DDC), 20-60 s warm **[unverified]** | Keep one editor alive under MCP |

### 6.2 Memory and disk

- Editor RSS for a small city scene: 6-12 GB; a cook or shader compile spawns workers using most cores and several GB more. With 30 GB RAM, do **not** run Blender MPFB builds concurrently with the editor; extend `with_cpu.sh` with a memory-aware slot or a second lock. Add a 32 GB swapfile before any source build.
- Disk: prebuilt 43 GB + DDC 10-30 GB + project with imported assets 5-20 GB ≈ 60-100 GB; source build 225+ GB. Put the engine on the NVMe.

### 6.3 Licence / royalty

- UE EULA: free to use; 5% royalty on gross revenue above the first **$1,000,000 lifetime per product** (unrealengine.com/eula/unreal, unrealengine.com/license; EULA page returned 403 to the fetcher, terms taken from Epic's licence summary and CG Channel 2024-10). "Launch Everywhere with Epic" cuts it to **3.5%** for titles that launch on EGS day-and-date (from 2025-01-01). Godot is MIT: nothing to pay.
- MetaHuman: under the UE EULA since 2025-06-04; can be used in any engine; cannot be used to train AI models; over $1M/year non-game use needs $1,850 seats.
- Fab Standard licence: Personal (< $100k gross in 12 months) vs Professional tiers, per-asset; the Unreal-only free content stays Unreal-only; `NoAI` tag assets must not be used for generative AI training. Megascans are no longer broadly free (since 2025).

### 6.4 Linux-specific risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Vulkan device-lost / driver regressions after a CachyOS update | Medium | Pin `nvidia` package; keep a known-good driver; `-NoRaytracing` triage |
| Editor UI on Wayland (SDL3) | Low on 5.8.3, high on 5.7 | `SDL_VIDEODRIVER=x11`, `Slate.EnableTooltips=False` |
| No Live Coding; Hot Reload corrupts state | Certain | Restart-per-change or Angelscript; keep logic data-driven |
| Interchange glTF skin weights capped at 4 | Certain until UE-392966 ships | Limit MPFB influences to 4 or export FBX |
| Binary assets vs agent review | Certain | OFPA, JSON sources, `.utxt` export for review, Python regenerators |
| Plugin availability (Fab plugins Windows-only) | Medium | Prefer engine plugins; build source plugins ourselves |
| Epic MCP plugin is experimental | Medium | Pin 5.8.3; wrap calls in our skills; commit before sessions |
| RAM pressure with Blender + editor | High | Serialize via locks; swapfile |
| Angelscript fork behind 5.8 or heavy to build | Unknown | Verify branch/version on day 0 (needs Epic org link); treat as a second spike |

---

## 7. Recommended 3-day spike

Precondition (day 0, ~2 h): Epic account; link GitHub to EpicGames org (for source access later); download 5.8.3 Linux
zip to `/opt/UE_5.8` (NVMe); `nvidia-smi` shows ≥ 570; `vulkaninfo | grep -i mesh_shader`; 32 GB swapfile; install
the official Claude Code plugin.

**Day 1: install, import, light.**
1. Launch editor once (X11 env if Wayland misbehaves), create `Krakow.uproject` as a C++ project with `ModelContextProtocol`, `AllToolsets`, `PythonScriptPlugin`, `EditorScriptingUtilities`, `Interchange*`, `MovieRenderPipeline` enabled; enable OFPA + World Partition; set `bAutoStartServer`. Commit.
2. `ue-build` skill: time a clean build and an incremental one-line change (record numbers in this doc).
3. `ue-import`: import the city glTFs (Cloth Hall, St Mary's, streets) and 20 MPFB characters with morph targets; log any 4-influence artefacts.
4. Place SkyAtmosphere, VolumetricCloud, height fog, directional sun/moon from Python using `data/sky.json`; Lumen on; MegaLights for lanterns.
5. `ue-shot`: one offscreen screenshot set at three times of day.

**Day 2: stealth core + one mission from data.**
1. C++ module `KrakowCore`: JSON loader for `data/stealth.json`, `missions.json`, `npcs.json` (FJsonObjectConverter into USTRUCTs); `UStealthSubsystem` (visibility from posture, sampled light, noise), `AGuard` with two-zone cone and alert phases, hiding spots, `UMissionSubsystem` running *The Printer's Bundle* from data.
2. If C++ turnaround is >2 min per change by day-2 noon, switch the gameplay layer to the Angelscript fork (source build overnight) or stop the spike with a "no unless Angelscript" verdict.
3. Player pawn with crouch/prone/lean; minimal Slate HUD.

**Day 3: headless smoke, screenshot route, side-by-side.**
1. `ue-test`: `Automation RunTests Krakow.*` covering data load, mission graph, stealth maths; parse `index.json`; run under `with_cpu.sh`.
2. `ue-shot` route matching `tools/refresh_screenshots.sh` cameras; produce `docs/screenshots/ue/`.
3. Side-by-side with Godot shots (same time of day, same street); FPS at 1920x1080; RSS and disk usage; total lines of C++/Python written by agents vs GDScript.

**Go / no-go criteria**

| Criterion | Go | No-go |
|---|---|---|
| Editor + `-game` stable on this GPU/driver for a day | no device-lost crashes | any repeatable crash without a workaround |
| Incremental C++ (or Angelscript) change to visible result | ≤ 90 s (C++) or ≤ 10 s (Angelscript) | > 3 min |
| Headless smoke round-trip | ≤ 60 s warm, parsed pass/fail | > 3 min or unparseable |
| Offscreen screenshot set | works under `with_gpu.sh`, ≤ 2 min | needs a visible window |
| Import fidelity | 20 characters with morphs and ≤ 4-influence skinning look right; city loads | visible skin breakage or morphs lost |
| Fidelity gain | Lumen + atmosphere + MegaLights clearly better than the Godot look at ≥ 60 fps | not clearly better, or < 30 fps |
| Agent ergonomics | agents complete day-2 tasks through skills + MCP without manual editor clicks | > 3 manual GUI interventions per day |

---

## 8. Command cheat-sheet (Linux, paths to confirm after install)

```bash
UE=/opt/UE_5.8                                   # TODO confirm
P=$PWD/unreal/Krakow.uproject                    # TODO confirm
ED=$UE/Engine/Binaries/Linux/UnrealEditor-Cmd
COMMON="-unattended -nop4 -nosplash -nosound -stdout -FullStdOutLogOutput"

# build editor target (UBT)
$UE/Engine/Build/BatchFiles/Linux/Build.sh KrakowEditor Linux Development -Project=$P -Progress -NoHotReloadFromIDE
# headless python
$ED $P -run=pythonscript -script=/abs/tools/ue/sync_data.py -nullrhi $COMMON
# python with full editor init (exits after script)
$ED $P -ExecutePythonScript=/abs/tools/ue/import_city.py -nullrhi $COMMON
# automation tests (exit code always 0 -> parse index.json)
$ED $P -nullrhi $COMMON -ExecCmds="Automation RunTests Krakow" -TestExit="Automation Test Queue Empty" -ReportExportPath=/tmp/ue-report -log
# offscreen screenshot via console commands (needs GPU lock)
tools/with_gpu.sh $ED $P /Game/Maps/City -game -RenderOffscreen -resx=1920 -resy=1080 $COMMON \
  -ExecCmds="r.SetRes 1920x1080; HighResShot 1920x1080 filename=/tmp/shots/rynek.png; Quit"
# movie render queue from CLI
tools/with_gpu.sh $ED $P /Game/Maps/City -game -RenderOffscreen -MoviePipelineConfig=/Game/Cine/Q_Shots -windowed -resx=1920 -resy=1080 -log
# cook + package Linux client
$UE/Engine/Build/BatchFiles/RunUAT.sh BuildCookRun -project=$P -platform=Linux -clientconfig=Development \
  -cook -stage -pak -archive -archivedirectory=$PWD/export/ue -unattended -utf8output -nop4
# keep one editor alive with MCP + remote python
SDL_VIDEODRIVER=x11 $UE/Engine/Binaries/Linux/UnrealEditor $P -ModelContextProtocolStartServer -log
# then: curl -s http://127.0.0.1:8000/mcp  (Epic MCP)  |  Remote Control: http://127.0.0.1:30010/remote/info
```

Log grep for failure: `grep -E "Error:|Fatal error|LogAutomationController.*(Failed|Error)|Assertion failed" run.log`.
