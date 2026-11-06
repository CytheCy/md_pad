#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
launcher_dir="${HOME}/.local/bin"
desktop_dir="${HOME}/.local/share/applications"
icon_theme_dir="${HOME}/.local/share/icons/hicolor"
icon_dir="${icon_theme_dir}/scalable/apps"

python3 -m venv --system-site-packages "${project_dir}/.venv"
"${project_dir}/.venv/bin/python" -m pip install -r "${project_dir}/requirements.txt"
mkdir -p "${launcher_dir}" "${desktop_dir}" "${icon_dir}"
install -m 644 "${project_dir}/md_pad_icon.svg" "${icon_dir}/md-pad.svg"

cat > "${launcher_dir}/pad" <<EOF
#!/usr/bin/env bash
exec "${project_dir}/.venv/bin/python" "${project_dir}/main.py" "\$@"
EOF
chmod +x "${launcher_dir}/pad"

cat > "${desktop_dir}/pad.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MDPad
Comment=Edit Markdown and text notes
Exec=${launcher_dir}/pad %f
Icon=md-pad
Terminal=false
Categories=Utility;TextEditor;
MimeType=text/plain;text/markdown;
EOF

if command -v update-desktop-database >/dev/null; then
    update-desktop-database "${desktop_dir}"
fi
if command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -f -t "${icon_theme_dir}"
fi
echo "MDPad installed. Launch it from KDE's application menu or run ${launcher_dir}/pad."
