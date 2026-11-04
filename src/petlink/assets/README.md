# PetLink character assets

Original AI-generated PNG atlases created with the built-in image generator
on 2026-11-04 using the user-supplied PetLink reference. No third-party character
pack or animation runtime is bundled. Generation does not establish exclusive
copyright or independently verify ownership of the supplied reference.

## Layer layout

Each atlas has two columns. The row split is 56% of image height to accommodate
the larger heads. The loader trims transparent space and small isolated edge
speckles once, then caches pixmaps. PNG alpha is preserved.

| Asset | Upper left | Upper right | Lower left | Lower right |
| --- | --- | --- | --- | --- |
| ishu.png | Blank face, cloud hair, headphones, orb | Lavender cape/body/feet | Spare star bow | Mitten |
| coral.png | Blank face, pink hair, mint hood, flower/sprout | Mint cape/body/feet | Spare pink bow | Mitten |
| lola.png | Blank cat face, goggles/star; no ears | Scarf/body/feet | Two ears | Tail |

The two ears are split and cached independently. Eyes, pupils, highlights,
eyebrows, blush, mouth and cat paws are drawn by Qt, separately from the art.
Hair/headphones are currently baked into each head; cape and bow are baked into
each body. They follow their parent layer, not independent deformation rigs.
The spare bow tiles are retained for a future body-art revision.

## Generation prompt set

Shared prompt: Use the supplied reference as character design guidance. Create
a transparent production animation atlas with a strict two-by-two layout and
generous transparent space around isolated parts. Front-facing premium painted
chibi game style, pastel gradients, highlights and soft outlines. No background,
labels, borders, floor or shadow ellipse. Top-left isolated head with a blank
pale face: no eyes, eyebrows, mouth or nose. Top-right isolated headless body
with feet, no arms. Lower-left accessory, lower-right isolated limb.

Ishu: preserve the reference's blue cloud hair, lavender headphones and orb,
purple cape with stitched stars, gold star bow, tiny dark feet and mitten.

Coral: preserve pink fluffy hair, mint hood/headphones, pink flower, sprout,
mint body, pastel cape, pink star ribbon, tiny dark feet and mint mitten.

Lola: preserve navy fluffy cat head, goggles, forehead star and cream face;
omit ears from head. Separate gold scarf/bell body, feet and satchel; no arms
or tail. Lower-left contains two separate pink-lined ears, lower-right one
curved fluffy navy tail with white tip.
