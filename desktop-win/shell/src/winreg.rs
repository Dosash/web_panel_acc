//! Немного реестра: автозапуск (Run), имя и значок для уведомлений (AppUserModelId), сведения установщика.

use windows::core::HSTRING;
use windows::Win32::Foundation::ERROR_SUCCESS;
use windows::Win32::System::Registry::{
    RegDeleteKeyValueW, RegGetValueW, RegSetKeyValueW, HKEY, HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, REG_SZ,
    RRF_RT_REG_SZ, RRF_SUBKEY_WOW6464KEY,
};

pub const HKCU: HKEY = HKEY_CURRENT_USER;
pub const HKLM: HKEY = HKEY_LOCAL_MACHINE;

pub fn get_string(root: HKEY, key: &str, name: &str) -> Option<String> {
    let (key, name) = (HSTRING::from(key), HSTRING::from(name));
    let mut size: u32 = 0;
    unsafe {
        let flags = RRF_RT_REG_SZ | RRF_SUBKEY_WOW6464KEY;
        if RegGetValueW(root, &key, &name, flags, None, None, Some(&mut size)) != ERROR_SUCCESS {
            return None;
        }
        let mut buf = vec![0u16; (size as usize).div_ceil(2) + 1];
        if RegGetValueW(root, &key, &name, flags, None, Some(buf.as_mut_ptr().cast()), Some(&mut size)) != ERROR_SUCCESS {
            return None;
        }
        let len = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
        Some(String::from_utf16_lossy(&buf[..len]))
    }
}

pub fn set_string(root: HKEY, key: &str, name: &str, value: &str) -> windows::core::Result<()> {
    let data: Vec<u16> = value.encode_utf16().chain(std::iter::once(0)).collect();
    unsafe {
        RegSetKeyValueW(
            root,
            &HSTRING::from(key),
            &HSTRING::from(name),
            REG_SZ.0,
            Some(data.as_ptr().cast()),
            (data.len() * 2) as u32,
        )
        .ok()
    }
}

pub fn delete_value(root: HKEY, key: &str, name: &str) {
    unsafe {
        let _ = RegDeleteKeyValueW(root, &HSTRING::from(key), &HSTRING::from(name));
    }
}
