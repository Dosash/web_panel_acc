fn main() {
    // версия программы — VERSION из app/config.py (единственный источник; build.ps1 подставляет её
    // и в сведения о файле через --config)
    println!("cargo:rerun-if-changed=../../app/config.py");
    let config = std::fs::read_to_string("../../app/config.py").expect("не прочитать app/config.py");
    let version = config
        .lines()
        .find_map(|l| l.strip_prefix("VERSION = \"")?.strip_suffix('"'))
        .expect("в app/config.py нет VERSION");
    println!("cargo:rustc-env=TG_PANEL_VERSION={version}");
    tauri_build::build();
}
