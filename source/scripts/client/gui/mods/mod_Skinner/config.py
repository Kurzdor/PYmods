# -*- coding: utf-8 -*-
import BigWorld
import Keys
import ResMgr
from PYmodsCore import PYmodsConfigInterface, refreshCurrentVehicle, checkKeys, loadJson, remDups, objToDict
from PYmodsCore.delayed import showI18nDialog, g_modsListApi
from gui import SystemMessages
from gui.Scaleform.framework import ScopeTemplates, ViewSettings, WindowLayer, g_entitiesFactories
from gui.Scaleform.framework.entities.abstract.AbstractWindowView import AbstractWindowView
from gui.Scaleform.framework.managers.loaders import SFViewLoadParams
from gui.shared.personality import ServicesLocator as SL
from helpers import dependency
from skeletons.gui.shared.utils import IHangarSpace
from . import __date__, __modID__


class ConfigInterface(PYmodsConfigInterface):
    hangarSpace = dependency.descriptor(IHangarSpace)
    # noinspection PyUnusedLocal
    defaultSkinConfig = property(lambda self: {
        'static': {'player': True, 'ally': True, 'enemy': True},
        'dynamic': {'player': False, 'ally': True, 'enemy': True}})

    def __init__(self):
        self.teams = ('player', 'ally', 'enemy')
        self.settings = {}
        self.skinsCache = {'CRC32': '', 'version': ''}
        self.skinsData = {
            'models': {},
            'priorities': {skinType: {'player': [], 'ally': [], 'enemy': []} for skinType in ('static', 'dynamic')}}
        self.isModAdded = False
        self.dynamicSkinEnabled = False
        self.currentTeam = self.teams[0]
        super(ConfigInterface, self).__init__()

    def init(self):
        self.ID = __modID__
        self.version = '1.1.4 (%s)' % __date__
        self.defaultKeys = {'DynamicSkinHotkey': [Keys.KEY_F1, [Keys.KEY_LCONTROL, Keys.KEY_RCONTROL]],
                            'ChangeViewHotkey': [Keys.KEY_F2, [Keys.KEY_LCONTROL, Keys.KEY_RCONTROL]]}
        self.data = {'enabled': True,
                     'isDebug': True,
                     'DynamicSkinHotkey': self.defaultKeys['DynamicSkinHotkey'],
                     'ChangeViewHotkey': self.defaultKeys['ChangeViewHotkey']}
        self.i18n = {
            'UI_description': 'Skinner',
            'UI_flash_header': 'Skins setup',
            'UI_flash_header_tooltip': "Setup for Skinner by <font color='#DD7700'><b>Polyacov_Yury</b></font>",
            'UI_flash_skinSetup': 'Skin setup',
            'UI_flash_skinPriority': 'Skin priorities',
            'UI_flash_skinSetupBtn': 'Setup',
            'UI_flash_skinPriorityBtn': 'Priorities',
            'UI_flash_skinType_static': 'Static',
            'UI_flash_skinType_dynamic': 'Dynamic',
            'UI_flash_team_player': 'Player',
            'UI_flash_team_ally': 'Ally',
            'UI_flash_team_enemy': 'Enemy',
            'UI_flash_useFor_header_text': 'Use this item for:',
            'UI_flash_useFor_player_text': 'Player',
            'UI_flash_useFor_ally_text': 'Allies',
            'UI_flash_useFor_enemy_text': 'Enemies',
            'UI_flash_saveBtn': 'Save',
            'UI_flash_unsaved_header': 'Unsaved settings',
            'UI_flash_unsaved_text': 'Unsaved setting changes detected. Do you want to save them?',
            'UI_loading_autoLogin': 'Log in afterwards',
            'UI_loading_autoLogin_cancel': 'Cancel auto login',
            'UI_loading_done': ' Done!',
            'UI_loading_header_CRC32': 'Skinner: checking textures',
            'UI_loading_header_models_clean': 'Skinner: cleaning models',
            'UI_loading_header_models_unpack': 'Skinner: unpacking models',
            'UI_loading_package': 'Unpacking %s:',
            'UI_loading_skinPack': 'Checking %s:',
            'UI_loading_skinPack_clean': 'Cleaning %s:',
            'UI_loading_skins': 'Checking skins...',
            'UI_loading_skins_clean': 'Cleaning skin models...',
            'UI_restart_header': 'Skinner: restart',
            'UI_restart_text': (
                'Skin models have been re-unpacked.\nClient restart required to accept changes.\n'
                'Client proper behaviour <b>NOT GUARANTEED</b> until next client start.\n'
                'This will <b>not</b> be required later.\nDo you want to restart the game now?'),
            'UI_restart_button_restart': 'Restart',
            'UI_restart_button_shutdown': 'Shutdown',
            'UI_setting_isDebug_text': 'Enable extended log printing',
            'UI_setting_isDebug_tooltip': 'If enabled, your python.log will be harassed with mod\'s debug information.',
            'UI_setting_ChangeViewHotkey_text': 'View mode switch hotkey',
            'UI_setting_ChangeViewHotkey_tooltip': (
                'This hotkey will switch the preview mode in hangar.\n<b>Possible modes:</b>\n'
                ' • Player tank\n • Ally tank\n • Enemy tank'),
            'UI_setting_DynamicSkinHotkey_text': 'Dynamic skin display switch hotkey',
            'UI_setting_DynamicSkinHotkey_tooltip': (
                'This hotkey will switch dynamic skin preview mode in hangar.\n'
                '<b>Possible modes:</b>\n • OFF\n • Model add'),
            'UI_enableDynamicSkin': '<b>Skinner:</b>\nEnabling dynamic skins display.',
            'UI_disableDynamicSkin': '<b>Skinner:</b>\nDisabling dynamic skins display.',
            'UI_install_skin': '<b>Skinner:</b>\nSkin installed: ',
            'UI_install_skin_dynamic': '<b>Skinner:</b>\nDynamic skin installed: ',
            'UI_install_default': '<b>Skinner:</b>\nDefault model applied.',
            'UI_mode': '<b>Skinner:</b>\nCurrent display mode: ',
            'UI_mode_player': 'player tank preview',
            'UI_mode_ally': 'ally tank preview',
            'UI_mode_enemy': 'enemy tank preview'}
        super(ConfigInterface, self).init()

    def createTemplate(self):
        return {'modDisplayName': self.i18n['UI_description'],
                'enabled': self.data['enabled'],
                'column1': [self.tb.createHotKey('DynamicSkinHotkey')],
                'column2': [self.tb.createHotKey('ChangeViewHotkey'),
                            self.tb.createControl('isDebug')]}

    def onMSADestroy(self):
        try:
            from gui.mods import mod_remodenabler
        except ImportError:
            refreshCurrentVehicle()

    def onApplySettings(self, settings):
        super(ConfigInterface, self).onApplySettings(settings)
        if self.isModAdded:
            g_modsListApi.updateModification(id='SkinnerUI', enabled=self.data['enabled'] and bool(self.skinsData['models']))

    def migrateConfigs(self):
        settings = loadJson(self.ID, 'settings', self.settings, self.configPath)
        if settings.keys() == ['skins', 'skins_dynamic']:
            new_settings = {}
            for skinTypeName, skinTypeConf in settings.iteritems():
                skinType = skinTypeName.replace('skins', '')
                if not skinType:
                    skinType = 'static'
                else:
                    skinType = skinType[1:]
                for skinName, skinConf in skinTypeConf.iteritems():
                    skinSettings = new_settings.setdefault(skinName, {}).setdefault(skinType, {})
                    for setting in skinConf:
                        if 'swap' not in setting:
                            continue
                        new_setting = setting[4:].lower()
                        if new_setting not in self.teams:
                            print new_setting
                            assert False
                        skinSettings[new_setting] = skinConf[setting]
            loadJson(self.ID, 'settings', new_settings, self.configPath, True)
        priorities = loadJson(self.ID, 'skinsPriority', self.skinsData['priorities'], self.configPath)
        for skinType in ('static', 'dynamic'):
            priority = priorities[skinType]
            for key in priority.keys():
                if not key.islower():
                    priority[key.lower()] = priority.pop(key)
        loadJson(self.ID, 'skinsPriority', priorities, self.configPath, True)

    def readCurrentSettings(self, quiet=True):
        super(ConfigInterface, self).readCurrentSettings(quiet)
        self.settings = loadJson(self.ID, 'settings', self.settings, self.configPath)
        self.skinsCache.update(loadJson(self.ID, 'skinsCache', self.skinsCache, self.configPath))
        self.skinsData['priorities'] = loadJson(self.ID, 'skinsPriority', self.skinsData['priorities'], self.configPath)
        if self.data['isDebug']:
            print self.ID + ': loading skin configs:'
        skinDirSect = ResMgr.openSection('vehicles/skins/textures/')
        for sname in () if skinDirSect is None else remDups(skinDirSect.keys()):
            confDict = self.settings.setdefault(sname, self.defaultSkinConfig)
            self.skinsData['models'][sname] = pRecord = {'name': sname, 'whitelist': set()}
            vehiclesDirSect = skinDirSect[sname]['vehicles']
            for curNation in [] if vehiclesDirSect is None else remDups(vehiclesDirSect.keys()):
                nationDirSect = vehiclesDirSect[curNation]
                for vehicleName in [] if nationDirSect is None else remDups(nationDirSect.keys()):
                    vehDirSect = nationDirSect[vehicleName]
                    sections = {'default': vehDirSect}
                    modelsSetsSect = vehDirSect['_skins']
                    if modelsSetsSect is not None:
                        for modelsSet, modelsSetSect in modelsSetsSect.items():
                            sections[modelsSet] = modelsSetSect
                    for modelsSet, modelsSetSect in sections.items():
                        tracksDirSect = modelsSetSect['tracks']
                        if not any(texName.endswith('.dds') for texName in (
                                ([] if modelsSetSect is None else remDups(modelsSetSect.keys())) +
                                ([] if tracksDirSect is None else remDups(tracksDirSect.keys())))):
                            if self.data['isDebug']:
                                print self.ID + ':', vehicleName, 'folder from', sname, 'pack is empty.'
                        else:
                            pRecord['whitelist'].add((vehicleName + '/' + modelsSet).lower())
            for skinType in ('static', 'dynamic'):
                priorities = self.skinsData['priorities'][skinType]
                for tankType in priorities:
                    if not confDict[skinType][tankType]:
                        if self.data['isDebug']:
                            print self.ID + ':', tankType, 'swapping in', sname, 'disabled.'
                        if sname in priorities[tankType]:
                            priorities[tankType].remove(sname)
                    elif sname not in priorities[tankType]:
                        priorities[tankType].append(sname)
                if self.data['isDebug']:
                    print self.ID + ': config for', sname, 'loaded.'
        for sname in self.settings.keys():
            if sname not in self.skinsData['models']:
                del self.settings[sname]
        if not self.skinsData['models']:
            if not quiet:
                print self.ID + ': no skin packs found, skin module standing down.'
        for skinType in self.skinsData['priorities']:
            for key in self.skinsData['priorities'][skinType]:
                for sname in self.skinsData['priorities'][skinType][key]:
                    if sname not in self.skinsData['models']:
                        self.skinsData['priorities'][skinType][key].remove(sname)
        loadJson(self.ID, 'skinsPriority', self.skinsData['priorities'], self.configPath, True, quiet=quiet)
        loadJson(self.ID, 'settings', self.settings, self.configPath, True, quiet=quiet)
        self.updateMod()

    @property
    def collisionMode(self):
        try:
            from gui.mods.mod_remodenabler import g_config as re_config
            return re_config.collisionMode
        except ImportError:
            return 0

    def registerSettings(self):
        super(ConfigInterface, self).registerSettings()
        # noinspection PyArgumentList
        g_entitiesFactories.addSettings(
            ViewSettings('SkinnerUI', SkinnerUI, 'Skinner.swf', WindowLayer.WINDOW, None,
                         ScopeTemplates.GLOBAL_SCOPE, False))
        self.isModAdded = g_modsListApi.addModification(
            id='SkinnerUI', name=self.i18n['UI_flash_header'], description=self.i18n['UI_flash_header_tooltip'],
            icon='gui/flash/Skinner.png', enabled=self.data['enabled'] and bool(self.skinsData['models']), login=True,
            lobby=True, callback=lambda: (
                    SL.appLoader.getDefLobbyApp().containerManager.getContainer(WindowLayer.TOP_WINDOW).getViewCount()
                    or SL.appLoader.getDefLobbyApp().loadView(SFViewLoadParams('SkinnerUI')))) != NotImplemented

    def onHotkeyPressed(self, event):
        if (not hasattr(BigWorld.player(), 'databaseID') or not self.data['enabled'] or not event.isKeyDown()
                or self.isMSAOpen or not self.skinsData['models']):
            return
        if checkKeys(self.data['ChangeViewHotkey'], event.key):
            try:
                from gui.mods.mod_remodenabler import g_config as re_config
            except ImportError:
                re_config = None
            if re_config is None:
                newModeNum = (self.teams.index(self.currentTeam) + 1) % len(self.teams)
                self.currentTeam = self.teams[newModeNum]
                if self.data['isDebug']:
                    print self.ID + ': changing display mode to', self.currentTeam
                SystemMessages.pushMessage(
                    'temp_SM%s<b>%s</b>' % (self.i18n['UI_mode'], self.i18n['UI_mode_' + self.currentTeam]),
                    SystemMessages.SM_TYPE.Warning)
                refreshCurrentVehicle()
        if checkKeys(self.data['DynamicSkinHotkey'], event.key):
            enabled = self.dynamicSkinEnabled
            self.dynamicSkinEnabled = not enabled
            SystemMessages.pushMessage(
                'temp_SM' + self.i18n['UI_%sableDynamicSkin' % ('en' if not enabled else 'dis')],
                SystemMessages.SM_TYPE.CustomizationForGold)
            refreshCurrentVehicle()


class SkinnerUI(AbstractWindowView):
    def py_onRequestSettings(self):
        g_config.readCurrentSettings(not g_config.data['isDebug'])
        texts = {k[9:]: v for k, v in g_config.i18n.iteritems() if k.startswith('UI_flash_')}
        settings = {'skins': g_config.settings, 'priorities': g_config.skinsData['priorities']}
        self.flashObject.as_updateData(texts, settings)

    def py_checkSettings(self, settings):
        settings = objToDict(settings)
        if g_config.settings != settings['skins'] or g_config.skinsData['priorities'] != settings['priorities']:
            showI18nDialog(
                g_config.i18n['UI_flash_unsaved_header'], g_config.i18n['UI_flash_unsaved_text'], 'common/confirm',
                lambda confirm: (
                    (self.py_onSaveSettings(settings) if confirm else None), self.flashObject.as_onSettingsChecked()))
            return False
        else:
            return True

    def py_onSaveSettings(self, settings):
        settings = objToDict(settings)
        g_config.settings = settings['skins']
        loadJson(g_config.ID, 'settings', g_config.settings, g_config.configPath, True, quiet=not g_config.data['isDebug'])
        g_config.skinsData['priorities'] = settings['priorities']
        loadJson(g_config.ID, 'skinsPriority', g_config.skinsData['priorities'], g_config.configPath, True,
                 quiet=not g_config.data['isDebug'])
        g_config.readCurrentSettings(not g_config.data['isDebug'])
        refreshCurrentVehicle()

    def onWindowClose(self):
        self.destroy()

    @staticmethod
    def py_printLog(*args):
        for arg in args:
            print arg


g_config = ConfigInterface()
