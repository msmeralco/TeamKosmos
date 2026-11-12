# Sol motion reels

Intro (6 s) and outro (10 s), 1920×1080 at 30 fps, made with [HyperFrames](https://github.com/heygen-com/hyperframes).
Every frame is code: HTML and CSS for the layout, GSAP and a few seeded canvas functions for the motion, so any frame can be rendered on its own.

```
sol-reel/index.html               intro  (the sun bounces in, hops up, and the title card appears)
sol-reel/compositions/outro.html  outro  (roof to rewards, passport and vouchers, the PDF plan, end card)
sol-reel/assets/reel.js           shared deterministic drawing code (bounce physics and helpers)
make_audio.py                     synthesises the music and sound design (seeded, so it is reproducible)
```

Needs Node 22+, FFmpeg (`brew install ffmpeg`) and the HyperFrames Chrome (`npx hyperframes browser ensure`).

```
cd sol-reel
npm run audio        # regenerate assets/intro.wav and outro.wav
npm run check        # lint, runtime, layout and contrast gate (intro)
npm run render:all   # renders/sol-intro.mp4 and renders/sol-outro.mp4
```

The numbers on screen come from the demo household (Reyes Family, synthetic data). Vouchers are samples.
