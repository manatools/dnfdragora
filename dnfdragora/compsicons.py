from gettext import gettext as _
import os.path

class CompsIcons:
    '''
    This class manages the access to group name and icons
    '''
    def __init__(self, icon_path=None):

        if icon_path:
            self.icon_path = icon_path if icon_path.endswith("/") else icon_path + "/"
        else:
            self.icon_path = "/usr/share/pixmaps/comps/"

        self.default_icon = self.icon_path + "uncategorized.png"

        # workaround for https://github.com/timlau/dnf-daemon/issues/9
        # generated using tools/gen-comps-category-list.sh
        self.name_to_id_map = {
            "KDE Desktop": "kde-desktop-environment",
            "Xfce Desktop": "xfce-desktop-environment",
            "Applications": "apps",
            "LXDE Desktop": "lxde-desktop-environment",
            "LXQt Desktop": "lxqt-desktop-environment",
            "Cinnamon Desktop": "cinnamon-desktop-environment",
            "MATE Desktop": "mate-desktop-environment",
            "Hawaii Desktop": "hawaii-desktop-environment",
            "Sugar Desktop Environment": "sugar-desktop-environment",
            "GNOME Desktop": "gnome-desktop-environment",
            "Development": "development",
            "Servers": "servers",
            "Base System": "base-system",
            "Content": "content",
            }

    def icon(self, group_path):
        group_names = group_path.split("/")
        for group_name in reversed(group_names):
            if group_name in self.name_to_id_map:
                group_id = self.name_to_id_map[group_name]
            else:
                group_id = group_name

            icon_name = self.icon_path + group_id + ".png"
            if os.path.exists(icon_name):
                return icon_name

        return self.default_icon
