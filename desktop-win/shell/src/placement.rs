//! Размер и положение окна между запусками: GetWindowPlacement/SetWindowPlacement — с обычным размером
//! развёрнутого окна и поправкой Windows, если монитора, где было окно, больше нет.

use tauri::WebviewWindow;
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::UI::WindowsAndMessaging::{
    GetWindowPlacement, IsZoomed, SetWindowPlacement, SW_HIDE, WINDOWPLACEMENT,
};

fn hwnd(window: &WebviewWindow) -> Option<HWND> {
    Some(HWND(window.hwnd().ok()?.0 as _))
}

/// «левый верх правый низ развёрнуто» — в координатах рабочей области, как отдаёт Windows.
pub fn save(window: &WebviewWindow) -> Option<String> {
    let hwnd = hwnd(window)?;
    let mut wp = WINDOWPLACEMENT { length: std::mem::size_of::<WINDOWPLACEMENT>() as u32, ..Default::default() };
    unsafe { GetWindowPlacement(hwnd, &mut wp).ok()? };
    let r = wp.rcNormalPosition;
    let maximized = unsafe { IsZoomed(hwnd).as_bool() };
    Some(format!("{} {} {} {} {}", r.left, r.top, r.right, r.bottom, maximized as u8))
}

/// Ставит сохранённое положение скрытому окну. true — окно было развёрнуто на весь экран.
pub fn restore(window: &WebviewWindow, saved: &str) -> bool {
    let n: Vec<i32> = saved.split_whitespace().filter_map(|s| s.parse().ok()).collect();
    let (Some(hwnd), [left, top, right, bottom, max]) = (hwnd(window), n.as_slice()) else { return false };
    if right - left < 200 || bottom - top < 200 {
        return false;
    }
    let wp = WINDOWPLACEMENT {
        length: std::mem::size_of::<WINDOWPLACEMENT>() as u32,
        showCmd: SW_HIDE.0 as u32,
        ptMinPosition: POINT { x: -1, y: -1 },
        ptMaxPosition: POINT { x: -1, y: -1 },
        rcNormalPosition: RECT { left: *left, top: *top, right: *right, bottom: *bottom },
        ..Default::default()
    };
    unsafe {
        let _ = SetWindowPlacement(hwnd, &wp);
    }
    *max == 1
}
