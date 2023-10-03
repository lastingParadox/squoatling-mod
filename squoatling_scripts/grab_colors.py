import commentjson
import os
from pathlib import Path
from PIL import Image

thisScriptPath = Path(__file__).resolve()
modfolder = Path(thisScriptPath.parent.parent)
speciesfile = modfolder.joinpath('species/squoatling.species')
skinsfolder = thisScriptPath.parent.joinpath('skins')

color_dict = [
    {
        "original_color": "CDBC89",
        "position": [9, 1],
        "description": "Primary Fur Color"
    },
    {
        "original_color": "D9CFAC",
        "position": [9, 7],
        "description": "Secondary Fur Color"
    },
    {
        "original_color": "897A4B",
        "position": [9, 0],
        "description": "Lighter Outline"
    },
    {
        "original_color": "72643E",
        "position": [4, 9],
        "description": "Darker Outline"
    },
    {
        "original_color": "AF7E55",
        "position": [10, 7],
        "description": "Hoof / Snout Color"
    },
    {
        "original_color": "7F5B3E",
        "position": [1, 19],
        "description": "Dark Hoof Outline"
    },
    {
        "original_color": "5E432E",
        "position": [7, 29],
        "description": "Darker Hoof Outline"
    },
    {
        "original_color": "DED19F",
        "position": [2, 1],
        "description": "Horn Color"
    },
    {
        "original_color": "968F72",
        "position": [2, 0],
        "description": "Horn Outline"
    },
    {
        "original_color": "F2E6C1",
        "position": [7, 13],
        "description": "Breast Tint"
    }
]

eye_dict = [
    {
        "original_color": "FACF20",
        "position": [7, 5],
        "description": "Light Eye Color"
    },
    {
        "original_color": "CFA100",
        "position": [7, 6],
        "description": "Eye Color"
    },
    {
        "original_color": "AB7D00",
        "position": [10, 6],
        "description": "Dark Eye Color"
    }
]

with open(speciesfile) as f:
    species = commentjson.load(f)

bodyColor = []
eyeColor = []

for filename in os.listdir(skinsfolder):
    bodyColors = {}
    eyeColors = {}

    img = Image.open(skinsfolder.joinpath(filename))
    rgb_img = img.convert("RGB")

    for color in color_dict:
        x = color["position"][0]
        y = color["position"][1]
        r, g, b = rgb_img.getpixel((x, y))

        bodyColors[color["original_color"]] = f"{r:02x}{g:02x}{b:02x}".upper()

    for color in eye_dict:
        x = color["position"][0]
        y = color["position"][1]
        r, g, b = rgb_img.getpixel((x, y))

        eyeColors[color["original_color"]] = f"{r:02x}{g:02x}{b:02x}".upper()
    
    bodyColor.append(bodyColors)
    eyeColor.append(eyeColors)

print("Body Colors\n", bodyColor)
print("Eye Colors\n", eyeColor)

species["bodyColor"] = bodyColor
species["undyColor"] = eyeColor

with open(speciesfile, 'w') as f:
    commentjson.dump(species, f, indent=2)
