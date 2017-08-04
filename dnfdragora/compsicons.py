import os.path

class CompsIcons:
    '''
    This class manages the access to group name and icons
    '''
    def __init__(self, rpm_groups, icon_path=None):

        if icon_path:
            self.icon_path = icon_path if icon_path.endswith("/") else icon_path + "/"
        else:
            self.icon_path = "/usr/share/pixmaps/comps/"

        self.default_icon = self.icon_path + "uncategorized.png"

        # workaround for https://github.com/timlau/dnf-daemon/issues/9
        # generated using tools/gen-comps-category-list.sh
        self._group_info = {
            "KDE Desktop": {"title": _("KDE Desktop"), "icon" :"kde-desktop-environment.png"},
            "Xfce Desktop": {"title": _("Xfce Desktop"), "icon" :"xfce-desktop-environment.png"},
            "Applications": {"title": _("Applications"), "icon" :"apps.png"},
            "LXDE Desktop": {"title": _("LXDE Desktop"), "icon" :"lxde-desktop-environment.png"},
            "LXQt Desktop": {"title": _("LXQt Desktop"), "icon" :"lxqt-desktop-environment.png"},
            "Cinnamon Desktop": {"title": _("Cinnamon Desktop"), "icon" :"cinnamon-desktop-environment.png"},
            "MATE Desktop": {"title": _("MATE Desktop"), "icon" :"mate-desktop-environment.png"},
            "Hawaii Desktop": {"title": _("Hawaii Desktop"), "icon" :"hawaii-desktop-environment.png"},
            "Sugar Desktop Environment": {"title": _("Sugar Desktop Environment"), "icon" :"sugar-desktop-environment.png"},
            "GNOME Desktop": {"title": _("GNOME Desktop"), "icon" :"gnome-desktop-environment.png"},
            "Development": {"title": _("Development"), "icon" :"development.png"},
            "Servers": {"title": _("Servers"), "icon" :"servers.png"},
            "Base System": {"title": _("Base System"), "icon" :"base-system.png"},
            "Content": {"title": _("Content"), "icon" :"content.png"},
            }

        self._getID_to_map(rpm_groups, self._group_info)

        # adding special groups
        if not 'All' in self._group_info.keys():
            self._group_info['All'] = {"title" : _("All")}
        if not 'Empty' in self._group_info.keys():
            self._group_info['Empty'] = {"title" : _("Empty")}
        if not 'Search' in self._group_info.keys():
            self._group_info['Search'] = {"title" : _("Search result")}

    def _getID_to_map(self, groups, group_info, g_id=None) :
        '''
        return id_to_name_map at run time
        '''
        gid = g_id
        for gl in groups:
            if (isinstance(gl, list)):
                if (type(gl[0]) is str) :
                    if not gid:
                        if not gl[0] in group_info.keys():
                            group_info[gl[0]] = { "title": gl[1], 'icon': gl[0] + ".png"}
                        gid = gl[0]
                    else:
                        if not gl[0] in group_info[gid].keys():
                            group_info[gid][gl[0]] = { "title": gl[1], 'icon': gl[0] + ".png"}
                else :
                    self._getID_to_map(gl, group_info, gid)

    @property
    def groups(self):
        '''
        return all the group info
        '''
        return self._group_info

    def icon(self, group_path):
        group_names = group_path.split("/")
        for group_name in reversed(group_names):
            icon_name = group_name + ".png"
            if group_name in self._group_info.keys():
                if ('icon' in self._group_info[group_name].keys()):
                    icon_name = self._group_info[group_name]['icon']

            icon_pathname = self.icon_path + icon_name
            if os.path.exists(icon_pathname):
                return icon_pathname

        return self.default_icon
