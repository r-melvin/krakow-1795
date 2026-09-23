#!/usr/bin/env bash
# Downloads the third-party animal source models (all CC0 except the hawk, CC-BY 3.0) into
# assets/third_party/<pack>/, keeping the original filenames. The raw downloads are git-ignored; only the
# LICENSE.txt files are committed. After fetching, build the game models with:
#   blender -b --python assets/blender/build_animals.py
# See docs/ANIMALS.md for sources and licences.
set -euo pipefail
cd "$(dirname "$0")/.."
TP=assets/third_party
OGA=https://opengameart.org/sites/default/files
PP=https://static.poly.pizza

fetch() {  # fetch <pack> <url> [<filename>]
	local pack=$1 url=$2 name=${3:-$(basename "$2")}
	mkdir -p "$TP/$pack"
	if [[ -s "$TP/$pack/$name" ]]; then
		echo "have  $pack/$name"
		return
	fi
	echo "fetch $pack/$name"
	curl -fsSL --retry 3 -o "$TP/$pack/$name.part" "$url"
	mv "$TP/$pack/$name.part" "$TP/$pack/$name"
}

# Horse: "Realtime Rancher's" horse by Lyndon Daniels, rigged by ChadM (OpenGameArt, CC0). 2k textures packed.
fetch oga_rigged_horse "$OGA/riggedHorse.blend"
# Dogs and cat: Quaternius "Ultimate Animated Animal Pack" via Poly Pizza (CC0): Wolf (hound base), Husky (spitz
# and cat base; build_animals.py reshapes, subdivides and furs them).
fetch quaternius_animals "$PP/f1d12388-e39b-4157-b32a-646a1d089fc4.glb"   # Wolf
fetch quaternius_animals "$PP/611d25c7-430f-4bb5-ab2c-d8f5f3cb9712.glb"   # Husky
# Pigeon: "Low poly 3D Pigeon model (rigged + animated)" by mujtaba-io (OpenGameArt, CC0).
fetch oga_pigeon "$OGA/genuinely-my-pigeon-extended-furthur.blend"
# Crow: "Raven" by Teh_Bucket (OpenGameArt, CC0).
fetch oga_raven "$OGA/raven_0.blend"
# Hawk: "Hawk Lp Rigged" by Sherkiz via Poly Pizza (CC-BY 3.0: credit required).
fetch polypizza_hawk "$PP/2a7aca61-a8f6-45f6-950e-003d4bfcab45.glb"
echo "done: $(du -sh "$TP" | cut -f1) in $TP"
