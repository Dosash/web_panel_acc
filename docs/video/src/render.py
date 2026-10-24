#!/usr/bin/env python3
"""Рендер демо-ролика TG Panel: кадры 1920×1080 из demo.html через Chromium (Playwright) и звук из Web Audio → MP4 через ffmpeg.

    uv run --with playwright python render.py --out demo.mp4          # полный ролик
    uv run --with playwright python render.py --frames shots --times 1,5,12   # отдельные кадры в PNG
    uv run --with playwright python render.py --step 4 --out draft.mp4 # черновик 15 fps

Нужны: /usr/bin/chromium (или --chromium), ffmpeg. Полный рендер — около 10 минут.
Результат кладётся в docs/video/demo.mp4; app.css и icons.js копируются из static/ при каждом запуске.
"""
import argparse, base64, functools, http.server, os, shutil, socketserver, subprocess, sys, time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def prepare():
    """Стили и иконки берутся из настоящей панели (static/), чтобы ролик не расходился с интерфейсом."""
    shutil.copy(os.path.join(ROOT, "static", "app.css"), os.path.join(HERE, "app.css"))
    js = open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8").read()
    i = js.index("const ICONS = {")
    j = js.index("\n};", i) + 3
    with open(os.path.join(HERE, "icons.js"), "w", encoding="utf-8") as f:
        f.write(js[i:j] + "\n")


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=HERE))
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd.server_address[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo.mp4")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float)
    ap.add_argument("--step", type=int, default=1, help="брать каждый N-й кадр (быстрый черновик)")
    ap.add_argument("--frames", help="папка для PNG-кадров (вместо видео)")
    ap.add_argument("--times", help="секунды через запятую — сохранить только эти кадры в --frames")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--chromium", default="/usr/bin/chromium")
    a = ap.parse_args()
    prepare()
    port = serve()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=a.chromium, args=["--no-sandbox", "--font-render-hinting=none", "--hide-scrollbars"])
        page = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1).new_page()
        page.on("console", lambda m: print("[page]", m.type, m.text, file=sys.stderr) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: print("[pageerror]", e, file=sys.stderr))
        page.goto(f"http://127.0.0.1:{port}/demo.html")
        page.wait_for_function("window.DEMO_READY === true", timeout=60000)
        dur = page.evaluate("DEMO.DUR")
        end = a.end if a.end is not None else dur
        audio_path = os.path.join(HERE, "audio.wav")
        if a.audio_only or (not a.no_audio and not a.frames):
            t0 = time.time()
            r = page.evaluate("renderAudio()")
            with open(audio_path, "wb") as f:
                f.write(base64.b64decode(r["wav"]))
            print(f"audio: {r['seconds']} s, peak {r['peak']}, rms {r['rms']} ({time.time() - t0:.1f} s)")
            if a.audio_only:
                return
        if a.times:
            os.makedirs(a.frames, exist_ok=True)
            for ts in a.times.split(","):
                t = float(ts)
                page.evaluate("t => renderAt(t)", t)
                page.screenshot(path=os.path.join(a.frames, f"t{t:06.2f}.png"))
            print("frames:", a.frames)
            return
        n0, n1 = round(a.start * a.fps), round(end * a.fps)
        frames = range(n0, n1, a.step)
        proc = None
        if a.frames:
            os.makedirs(a.frames, exist_ok=True)
        else:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", f"{a.fps}/{a.step}", "-i", "-"]
            if not a.no_audio:
                cmd += ["-ss", str(a.start), "-i", audio_path]
            cmd += ["-map", "0:v"] + ([] if a.no_audio else ["-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"])
            cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
                    "-movflags", "+faststart", "-t", f"{end - a.start:.4f}", a.out]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        t0 = time.time()
        for k, i in enumerate(frames):
            page.evaluate("t => renderAt(t)", i / a.fps)
            png = page.screenshot(type="png")
            if proc:
                proc.stdin.write(png)
            else:
                with open(os.path.join(a.frames, f"f{i:05d}.png"), "wb") as f:
                    f.write(png)
            if k % 120 == 0:
                el = time.time() - t0
                print(f"{k}/{len(frames)} кадров, {el:.0f} с, ~{el / (k + 1) * (len(frames) - k - 1):.0f} с осталось", flush=True)
        if proc:
            proc.stdin.close()
            rc = proc.wait()
            print("ffmpeg rc", rc, "→", a.out, f"({time.time() - t0:.0f} s)")
        browser.close()


if __name__ == "__main__":
    main()
