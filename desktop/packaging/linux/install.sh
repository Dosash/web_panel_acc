#!/usr/bin/env bash
# Установка TG Panel для текущего пользователя: программа в ~/.local/opt/tg-panel,
# ярлык в меню приложений, команда tg-panel. Удаление: ./install.sh --uninstall
# Данные (аккаунты) хранятся отдельно — в ~/.local/share/tg-panel — и при удалении не трогаются.
set -euo pipefail
SRC="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DEST="$HOME/.local/opt/tg-panel"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"

if [ "${1:-}" = "--uninstall" ]; then
  # и автозапуск, если его включали из трея — иначе при входе запускался бы удалённый файл
  rm -rf "$DEST" "$BIN/tg-panel" "$APPS/tg-panel.desktop" "$ICONS/tg-panel.png" \
    "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/tg-panel.desktop"
  echo "TG Panel удалена. Данные остались в ~/.local/share/tg-panel"
  exit 0
fi

if [ "$SRC" != "$DEST" ]; then
  rm -rf "$DEST"
  mkdir -p "$(dirname "$DEST")"
  cp -a "$SRC" "$DEST"
fi
mkdir -p "$BIN" "$APPS" "$ICONS"
ln -sf "$DEST/tg-panel" "$BIN/tg-panel"
cp "$DEST/tg-panel.png" "$ICONS/tg-panel.png"
sed "s|^Exec=.*|Exec=\"$DEST/tg-panel\"|" "$DEST/tg-panel.desktop" > "$APPS/tg-panel.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
echo "TG Panel установлена: меню приложений или команда tg-panel"
