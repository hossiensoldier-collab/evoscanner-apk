"""گرافیک تخصصی"""
from datetime import datetime
from pathlib import Path

DB = Path.home() / "evoscanner" / "knowledge.db"

GRAPHICS_LIBS = {
    "matplotlib":"2d-plot","seaborn":"2d-stats","plotly":"interactive",
    "bokeh":"interactive","altair":"declarative","pygal":"svg-charts",
    "pillow":"image-io","PIL":"image-io","opencv-python":"cv","cv2":"cv",
    "scikit-image":"cv","imageio":"image-io","moviepy":"video",
    "ffmpeg-python":"video","av":"video","pygame":"game-2d",
    "pyglet":"game-2d","arcade":"game-2d","moderngl":"opengl",
    "PyOpenGL":"opengl","pygfx":"webgpu","wgpu":"webgpu",
    "pythreejs":"3d-web","vtk":"3d-scientific","mayavi":"3d-scientific",
    "trimesh":"3d-mesh","open3d":"3d-point-cloud","manim":"animation-math",
    "pyrender":"3d-render","taichi":"gpu-graphics","numba-cuda":"gpu",
    "cupy":"gpu","cairo":"2d-vector","cairosvg":"svg","svglib":"svg",
    "turtle":"learning","tkinter":"gui","kivy":"gui-multi","pyqt":"gui",
    "pyside":"gui","wxpython":"gui","dash":"web-dashboard","panel":"web-dashboard",
    "streamlit":"web-dashboard","gradio":"web-ml-ui","vispy":"gpu-scientific",
    "glumpy":"gpu-scientific","pybullet":"3d-physics","pymunk":"2d-physics",
    "box2d":"2d-physics",
}

GRAPHICS_TOPICS = {
    "2d-plot":{"beginner":["line plot","scatter","bar chart","labels","legend"],
               "intermediate":["subplots","styles","colormaps","annotations"],
               "advanced":["custom backend","large data rendering"],
               "specialist":["GPU-accelerated plotting"]},
    "image-io":{"beginner":["open image","resize","save png"],
                "intermediate":["filters","compose","channels","crop"],
                "advanced":["batch processing","streaming"],
                "specialist":["10-bit color","ICC profiles"]},
    "cv":{"beginner":["read image","show window","gray"],
          "intermediate":["edge detect","contours","cascade"],
          "advanced":["optical flow","features","stereo"],
          "specialist":["real-time pipelines","GPU cv"]},
    "opengl":{"beginner":["create context","clear screen","draw triangle"],
              "intermediate":["shaders","buffers","textures"],
              "advanced":["framebuffers","geometry shaders","instancing"],
              "specialist":["compute shaders","vulkan interop"]},
    "gpu":{"beginner":["install cuda","hello gpu"],
           "intermediate":["kernels","memory model"],
           "advanced":["shared memory","streams"],
           "specialist":["cooperative groups","warp intrinsics"]},
    "3d-mesh":{"beginner":["load stl","display mesh"],
               "intermediate":["transform","boolean ops"],
               "advanced":["simplification","voxelization"],
               "specialist":["SDF","implicit surfaces"]},
    "3d-render":{"beginner":["scene","camera","light"],
                 "intermediate":["materials","shadows"],
                 "advanced":["PBR","deferred"],
                 "specialist":["ray tracing","neural rendering"]},
    "game-2d":{"beginner":["window","game loop","sprite"],
               "intermediate":["collision","animation","sound"],
               "advanced":["particles","tilemap"],
               "specialist":["optimization","physics engine"]},
    "animation-math":{"beginner":["first scene","fade in"],
                      "intermediate":["3d transform","latex"],
                      "advanced":["custom mobjects","graphs"],
                      "specialist":["render farms","4k output"]},
    "web-dashboard":{"beginner":["first app","slider"],
                     "intermediate":["data binding","callback"],
                     "advanced":["streaming","state management"],
                     "specialist":["real-time","websocket"]},
}


def graphics_scanners():
    queries = []
    for lib in GRAPHICS_LIBS:
        queries.append(f"{lib} python tutorial")
        queries.append(f"{lib} python advanced")
    for topic, levels in GRAPHICS_TOPICS.items():
        for lvl, items in levels.items():
            for item in items[:2]:
                queries.append(f"python {topic} {item}")
    return list(dict.fromkeys(queries))[:80]


def extract_graphics_topics(kb):
    conn = kb.conn
    n = 0
    rows = conn.execute(
        "SELECT hash,url,title,content FROM resources"
    ).fetchall()
    for h, url, title, content in rows:
        content = content or ""
        tl = (title or "").lower() + " " + content.lower()
        for lib, category in GRAPHICS_LIBS.items():
            if lib.lower() in tl:
                for lvl, items in GRAPHICS_TOPICS.get(category, {}).items():
                    for item in items[:3]:
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO graphics_topics"
                                "(topic,subtopic,level,description,source_url,library)"
                                " VALUES(?,?,?,?,?,?)",
                                (category, item, lvl,
                                 f"{lib}: {item}", url, lib))
                            n += 1
                        except Exception:
                            pass
        conn.commit()
    conn.commit()  # دوباره
    return n


def graphics_report(kb):
    conn = kb.conn
    print("\n=== Graphics Knowledge ===\n")
    rows = conn.execute(
        "SELECT library, COUNT(*) FROM graphics_topics "
        "GROUP BY library ORDER BY COUNT(*) DESC LIMIT 25").fetchall()
    if not rows:
        print("  (خالی — اول extract کن)")
        return
    for lib, n in rows:
        bar = "#" * min(n, 30)
        print(f"  {lib:20s} {n:4d}  {bar}")
    print("\n  بر اساس سطح:")
    for lvl, n in conn.execute(
        "SELECT level, COUNT(*) FROM graphics_topics "
        "GROUP BY level ORDER BY COUNT(*) DESC").fetchall():
        print(f"    {lvl:14s} {n:4d}")
    print("\n  بر اساس موضوع:")
    for topic, n in conn.execute(
        "SELECT topic, COUNT(*) FROM graphics_topics "
        "GROUP BY topic ORDER BY COUNT(*) DESC").fetchall():
        print(f"    {topic:20s} {n:4d}")


if __name__ == "__main__":
    from evoscanner_v2 import KB
    kb = KB()
    n = extract_graphics_topics(kb)
    print(f"✓ {n} موضوع گرافیک استخراج شد")
    graphics_report(kb)

