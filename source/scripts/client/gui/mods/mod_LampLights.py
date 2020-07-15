# -*- coding: utf-8 -*-
import BigWorld
import Keys
import Math
import ResMgr
import glob
import math_utils
import os
import traceback
from Avatar import PlayerAvatar
from PYmodsCore import PYmodsConfigInterface, loadJson, overrideMethod, checkKeys, sendMessage, Analytics, events
from Vehicle import Vehicle
from debug_utils import LOG_ERROR, LOG_NOTE
from functools import partial
from gui import SystemMessages
from vehicle_systems.CompoundAppearance import CompoundAppearance
from vehicle_systems.tankStructure import TankNodeNames, TankPartNames


def listToTuple(seq):
    return tuple(listToTuple(item) for item in seq) if isinstance(seq, list) else seq


class ConfigInterface(PYmodsConfigInterface):
    def __init__(self):
        self.isTickRequired = True
        self.configsDict = {}
        self.isLampsVisible = True
        self.modes = {'constant': [], 'stop': [], 'turn_left': [], 'turn_right': [], 'back': [], 'target': [], 'spot': []}
        super(ConfigInterface, self).__init__()

    def init(self):
        self.ID = '%(mod_ID)s'
        self.version = '2.2.3.1 (%(file_compile_date)s)'
        self.defaultKeys = {'hotkey': [Keys.KEY_F12]}
        self.data = {'enabled': True,
                     'enableAtStartup': True,
                     'hotkey': self.defaultKeys['hotkey'],
                     'enableMessage': True,
                     'Debug': False,
                     'DebugModel': False,
                     'DebugPath': ''}
        self.i18n = {
            'UI_description': 'Lamp Lights Enabler',
            'UI_activLamps': 'Lamps ENABLED',
            'UI_deactivLamps': 'Lamps DISABLED',
            'UI_setting_enableAtStartup_text': 'Lamps are enabled by default',
            'UI_setting_enableAtStartup_tooltip': 'Lamp lights will be added after battle loads.',
            'UI_setting_hotkey_text': 'LampLights hotkey',
            'UI_setting_hotkey_tooltip': 'Pressing this button in-battle toggles lamps on/off.',
            'UI_setting_enableMessage_text': 'Enable service channel message',
            'UI_setting_enableMessage_tooltip': (
                'This allows the mod to send a notification to service channel in no-GUI mode.'),
            'UI_setting_caps_text': 'Total configs loaded: {totalCfg}, light sources: {totalSrc}, models: {models}',
            'UI_setting_meta_text': 'Loaded configs:',
            'UI_setting_meta_tooltip': '%(meta)s',
            'UI_setting_meta_no_configs': 'No configs were loaded.',
            'UI_setting_meta_NDA': '{attachTo} • No data available or provided.',
            'UI_setting_meta_AND': ' and ',
            'UI_setting_attachToPlayer': 'player tanks',
            'UI_setting_attachToAlly': 'allies',
            'UI_setting_attachToEnemy': 'enemies',
            'UI_setting_attachTo': ' • Will be attached to ',
            'UI_serviceChannelPopUp': '<b>{author}<font color="#cc9933"> brought some light!</font></b>'}
        super(ConfigInterface, self).init()

    def createTemplate(self):
        sources = 0
        models = 0
        for confDict in self.configsDict.values():
            for source in confDict:
                if source not in ('enable', 'meta', 'attachToPlayer', 'attachToAlly', 'attachToEnemy'):
                    if 'model' not in confDict[source]['type']:
                        sources += 1
                    else:
                        models += 1

        metaList = []
        for fileName in sorted(self.configsDict.keys()):
            attaches = tuple(self.i18n['UI_setting_' + key] if self.configsDict[fileName][key] else ''
                             for key in ('attachToPlayer', 'attachToAlly', 'attachToEnemy'))
            if all(attaches):
                tooltipAttachTo = ''
            else:
                tooltipAttachTo = self.i18n['UI_setting_attachTo'] + self.i18n['UI_setting_meta_AND'].join(
                    filter(None, attaches)) + '\n'
            metaList.append('\n'.join((
                self.configsDict[fileName]['meta']['name'], self.configsDict[fileName]['meta']['desc'].format(
                    attachTo=tooltipAttachTo).rstrip())).rstrip())
        metaStr = ('\n'.join(metaList)) if metaList else self.i18n['UI_setting_meta_no_configs']
        capLabel = self.tb.createLabel('meta')
        capLabel['text'] = self.tb.getLabel('caps').format(totalCfg=len(self.configsDict), totalSrc=sources, models=models)
        capLabel['tooltip'] %= {'meta': metaStr}
        return {'modDisplayName': self.i18n['UI_description'],
                'enabled': self.data['enabled'],
                'column1': [self.tb.createControl('enableAtStartup'),
                            capLabel],
                'column2': [self.tb.createHotKey('hotkey'),
                            self.tb.createControl('enableMessage')]}

    def onApplySettings(self, settings):
        super(ConfigInterface, self).onApplySettings(settings)
        self.isLampsVisible = self.data['enabled'] and self.data['enableAtStartup'] and self.isLampsVisible

    def readConfDict(self, quiet, confdict, confPath, sourceModel=None, upperName=''):
        for confKey, configDict in confdict.items():
            if upperName:
                confKey = upperName + '.' + confKey
            if confKey in ('enable', 'meta', 'attachToPlayer', 'attachToAlly', 'attachToEnemy'):
                continue
            if any(confKey in curConfigsDict for curConfigsDict in self.configsDict.values()):
                print self.ID + ':', confPath + ': overlap detected:', confKey, 'already exists.'
                continue
            model = None
            if 'model' in configDict['type']:
                try:
                    model = BigWorld.Model(configDict['path'])
                except StandardError:
                    print 'LampLights: model path incorrect: %s' % configDict['path']
                    continue

            if not upperName:
                if configDict['place'] not in ('leftFront', 'rightFront', 'leftRear', 'rightRear',
                                               'hull', 'wheels_left', 'wheels_right', 'turret', 'spot'):
                    LOG_ERROR('Unknown place of %s: %s.' % (confKey, configDict['place']))
                    continue
            else:
                try:
                    sourceModel.node(configDict['place'])
                except ValueError:
                    LOG_ERROR('Unknown place of %s: %s.' % (confKey, configDict['place']))
                    continue
            if not configDict['visible']:
                if not quiet:
                    print self.ID + ':', confKey, 'disabled in config.'
                continue
            self.configsDict[os.path.basename(confPath).split('.')[0]][confKey] = confDict = {}
            for key in ('type', 'place', 'mode', 'preRotate', 'postRotate', 'vect'):
                confDict[key] = listToTuple(configDict[key])

            for key in ('attachToPlayer', 'attachToAlly', 'attachToEnemy'):
                confDict[key] = self.configsDict[os.path.basename(confPath).split('.')[0]][key]

            if confDict['mode'] not in self.modes:
                print self.ID + ': unknown mode in', confKey, 'detected:', confDict['mode'] + '. This light will be off.'
            else:
                self.modes[confDict['mode']].append(confKey)
            if 'model' not in confDict['type']:
                for key in ('colour', 'bright', 'innerRadius', 'outerRadius', 'dur', 'cs'):
                    confDict[key] = listToTuple(configDict[key])

                if confDict['type'] == 'spotLight':
                    confDict['ca'] = configDict['ca']
            else:
                confDict['path'] = configDict['path']
                if 'subLights' in configDict:
                    self.readConfDict(quiet, configDict['subLights'], confPath, sourceModel=model,
                                      upperName=confKey)
            if self.data['Debug'] and not quiet:
                print self.ID + ':', confKey, 'loaded.'

    def readCurrentSettings(self, quiet=True):
        self.configsDict.clear()
        self.modes = {'constant': [], 'stop': [], 'turn_left': [], 'turn_right': [], 'back': [], 'target': [], 'spot': []}
        super(ConfigInterface, self).readCurrentSettings(quiet)

        if self.data['DebugModel']:
            if self.data['DebugPath']:
                try:
                    _ = BigWorld.Model(self.data['DebugPath'])
                except StandardError:
                    LOG_ERROR('Debug model path incorrect: %s' % self.data['DebugPath'])
                    self.data['DebugModel'] = False

            else:
                LOG_NOTE('Debug disabled due to absence of DebugPath.')
                self.data['DebugModel'] = False
        if self.data['enabled']:
            configPath = self.configPath + 'configs/'
            if not os.path.exists(configPath):
                LOG_ERROR('%s config folder not found: %s' % (self.ID, configPath))
                os.makedirs(configPath)
            for confPath in glob.iglob(configPath + '*.json'):
                confName = os.path.basename(confPath)
                try:
                    confdict = loadJson(self.ID, confName.split('.')[0], self.configsDict.get(confName.split('.')[0], {}),
                                        os.path.dirname(confPath) + '/')
                except StandardError:
                    print self.ID + ': config', confName, 'is invalid.'
                    traceback.print_exc()
                    continue
                if not confdict['enable'] or not any(
                        x for x in (confdict.get(y, True) for y in ('attachToPlayer', 'attachToAlly', 'attachToEnemy'))):
                    if not quiet:
                        print self.ID + ': config', confName, 'is disabled.'
                    continue
                if self.data['Debug']:
                    print self.ID + ': loading', confName + ':'
                self.configsDict[confName.split('.')[0]] = configsDict = {}
                configsDict['meta'] = metaDict = {'name': '<b>%s</b>' % confName,
                                                  'desc': self.i18n['UI_setting_meta_NDA']}
                metaDict['name'] = confdict.get('meta', {}).get(self.lang, {}).get('name', metaDict['name'])
                metaDict['desc'] = confdict.get('meta', {}).get(self.lang, {}).get('desc', metaDict['desc'])
                for key in ['attachToPlayer', 'attachToAlly', 'attachToEnemy']:
                    configsDict[key] = confdict.get(key, True)
                self.readConfDict(quiet, confdict, confPath)

            if not self.configsDict:
                print 'LampLights has not loaded any configs. Are you sure you need this .pyc?'
            if self.data['DebugModel'] and self.configsDict:
                if self.data['Debug'] and not quiet:
                    print 'LampLights: loading configs for Debug:'
                for fileName, configsDict in self.configsDict.items():
                    for confKey in configsDict.keys():
                        if confKey in ('enable', 'meta', 'attachToPlayer', 'attachToAlly', 'attachToEnemy'):
                            continue
                        if configsDict.get(confKey + 'Debug') is None:
                            if 'model' not in configsDict[confKey]['type']:
                                self.configsDict[fileName][confKey + 'Debug'] = confDict = {}
                                confDict['type'] = 'model'
                                for key in ('place', 'preRotate', 'postRotate', 'vect', 'mode', 'attachToPlayer',
                                            'attachToAlly', 'attachToEnemy'):
                                    confDict[key] = listToTuple(configsDict[confKey][key])

                                if confDict['mode'] not in self.modes:
                                    print 'LampLights: unknown mode at %sDebug detected: %s. This light will be off.' \
                                          % (confKey, confDict['mode'])
                                else:
                                    self.modes[confDict['mode']].append(confKey + 'Debug')

                                confDict['path'] = self.data['DebugPath']
                                if self.data['Debug'] and not quiet:
                                    print 'LampLights: config for %sDebug loaded.' % confKey
                        elif self.data['Debug'] and not quiet:
                            print 'LampLights: debug assignment failure: %sDebug' % confKey

        else:
            LOG_NOTE('LampLights mod fully disabled via main config.')
            self.isLampsVisible = False
        self.isTickRequired = any(self.modes[key] for key in ('stop', 'turn_left', 'turn_right', 'back'))
        self.updateMod()

    def onHotkeyPressed(self, event):
        if (not hasattr(BigWorld.player(), 'arena') or not self.data['enabled']
                or not checkKeys(self.data['hotkey'], event.key) or not event.isKeyDown()):
            return
        self.isLampsVisible = not self.isLampsVisible
        if self.isLampsVisible:
            self.readCurrentSettings(not self.data['Debug'])
            for vehicleID in BigWorld.player().arena.vehicles:
                curVehicle = BigWorld.entity(vehicleID)
                if curVehicle is not None and curVehicle.isAlive():
                    lightsCreate(vehicleID, 'keyPress')

            sendMessage(self.i18n['UI_activLamps'])
        else:
            for vehicleID in lightDBDict.keys():
                lightsDestroy(vehicleID, 'keyPress')

            sendMessage(self.i18n['UI_deactivLamps'], 'Red')


_config = ConfigInterface()
if _config.data['enableMessage']:
    isLogin = True
    LOGIN_TEXT_MESSAGE = _config.i18n['UI_serviceChannelPopUp'].format(author='<font color="#DD7700">Polyacov_Yury</font>')


    @events.LobbyView.populate.after
    def new_Lobby_populate(*_, **__):
        global isLogin
        isRegistered = _config.ID in getattr(_config.MSAInstance, 'activeMods', ())
        if isLogin and not isRegistered:
            SystemMessages.pushMessage(LOGIN_TEXT_MESSAGE, type=SystemMessages.SM_TYPE.Information)
            isLogin = False


def nodeWatcher(section, nodeName, upperMat=math_utils.createIdentityMatrix()):
    retMat = None
    for curName, curSect in section.items():
        if curName == 'node':
            returnMat = Math.Matrix()
            returnMat.set(upperMat)
            returnMat.postMultiply(curSect['transform'].asMatrix)
            if curSect['identifier'].asString == nodeName:
                return returnMat
            retMat = nodeWatcher(curSect, nodeName, returnMat)
            if retMat is not None:
                return retMat

    return retMat


def findWheelNodes(vehicleID, place):
    nodeList = []
    nodeNamesList = []
    wheelsCount = 0
    wheelNodeStr = 'W_%s' % place
    subWheelNodeStr = 'WD_%s' % place
    vEntity = BigWorld.entity(vehicleID)
    vDesc = vEntity.typeDescriptor
    chassisSource = vDesc.chassis.models.undamaged
    modelSec = ResMgr.openSection(chassisSource)
    if modelSec is None:
        print chassisSource
        return [], []
    sourceSecStr = modelSec['nodefullVisual'].asString
    sourceSec = ResMgr.openSection(sourceSecStr + '.visual')
    if sourceSec is None:
        sourceSec = ResMgr.openSection(sourceSecStr + '.visual_processed')
    if sourceSec is None:
        print 'LampLights: visual not found for %s' % chassisSource
        return [], []
    while True:
        restoreMat = Math.Matrix()
        transMat = nodeWatcher(sourceSec, wheelNodeStr + str(wheelsCount))
        if transMat is not None:
            restoreMat.setTranslate(transMat.translation)
            nodeList.append(restoreMat)
            nodeNamesList.append(wheelNodeStr + str(wheelsCount))
            wheelsCount += 1
        else:
            break

    if not wheelsCount:
        while True:
            restoreMat = Math.Matrix()
            transMat = nodeWatcher(sourceSec, subWheelNodeStr + str(wheelsCount))
            if transMat is not None:
                restoreMat.setTranslate(transMat.translation)
                nodeList.append(restoreMat)
                nodeNamesList.append(subWheelNodeStr + str(wheelsCount))
                wheelsCount += 1
            else:
                break

    return [nodeList, nodeNamesList]


def computeTransform(confDict):
    matDict = {'preRotate': math_utils.createIdentityMatrix(),
               'postRotate': math_utils.createIdentityMatrix(),
               'vect': math_utils.createIdentityMatrix()}
    if any(isinstance(confDict[confKey][0], tuple) for confKey in matDict.keys()):
        for confKey in matDict.keys():
            if isinstance(confDict[confKey][0], tuple):
                keyframes = []
                for keyframe in confDict[confKey]:
                    timeStamp, value = keyframe
                    if 'vect' in confKey:
                        Mat = math_utils.createTranslationMatrix(value)
                    else:
                        Mat = math_utils.createRotationMatrix(value)
                    keyframes.append((timeStamp, Mat))
                MatAn = Math.MatrixAnimation()
                MatAn.keyframes = keyframes
                MatAn.time = 0.0
                MatAn.loop = True
            elif 'vect' in confKey:
                MatAn = math_utils.createTranslationMatrix(confDict[confKey])
            else:
                MatAn = math_utils.createRotationMatrix(confDict[confKey])
            matDict[confKey] = MatAn

        matProd = math_utils.MatrixProviders.product(matDict['vect'], matDict['postRotate'])
        LightMat = math_utils.MatrixProviders.product(matDict['preRotate'], matProd)
    else:
        preRotate = math_utils.createRotationMatrix(confDict['preRotate'])
        postRotate = math_utils.createRotationMatrix(confDict['postRotate'])
        LightMat = math_utils.createTranslationMatrix(confDict['vect'])
        LightMat.postMultiply(postRotate)
        LightMat.preMultiply(preRotate)
    return LightMat


lightDBDict = {}
fakesDict = {}
fakeMotorsDict = {}


# noinspection PyTypeChecker
def lightsCreate(vehicleID, callPlace=''):
    try:
        vehicle = BigWorld.player().arena.vehicles[vehicleID]
        vEntity = BigWorld.entity(vehicleID)
        if vEntity is None:
            return
        vDesc = vEntity.typeDescriptor
        if vehicleID == BigWorld.player().playerVehicleID:
            print 'LampLights: Create at %s' % callPlace
        constNodesList = [TankNodeNames.TRACK_LEFT_UP_FRONT,
                          TankNodeNames.TRACK_LEFT_UP_REAR,
                          TankNodeNames.TRACK_RIGHT_UP_FRONT,
                          TankNodeNames.TRACK_RIGHT_UP_REAR]
        compoundModel = vEntity.appearance.compoundModel
        nodeListML, nodeListNL = findWheelNodes(vehicleID, 'L')
        nodeListMR, nodeListNR = findWheelNodes(vehicleID, 'R')
        fakesDict[vehicleID] = fakeDict = {}
        fakeMotorsDict[vehicleID] = fakeMotorDict = {}

        sourcesDict = {TankPartNames.CHASSIS: None, TankPartNames.HULL: None}
        for tankPartName in sourcesDict.keys():
            curSource = getattr(vDesc, tankPartName).models.undamaged
            modelSec = ResMgr.openSection(curSource)
            if modelSec is None:
                print 'LampLights: file not found:', curSource
            sourceSecStr = modelSec['nodefullVisual'].asString
            sourceSec = ResMgr.openSection(sourceSecStr + '.visual')
            if sourceSec is None:
                sourceSec = ResMgr.openSection(sourceSecStr + '.visual_processed')
            if sourceSec is None:
                print 'LampLights: visual not found for', curSource
                print callPlace
            else:
                sourcesDict[tankPartName] = sourceSec
        HullMat = math_utils.createIdentityMatrix()
        deHullMat = math_utils.createIdentityMatrix()
        if sourcesDict[TankPartNames.CHASSIS] is not None:
            deHullMat = nodeWatcher(sourcesDict[TankPartNames.CHASSIS], 'V')
            deHullMat.invert()
        for tankPartName in (TankPartNames.CHASSIS, TankPartNames.HULL):
            fakeDict[tankPartName] = BigWorld.Model('objects/fake_model.model')
            fakeDict[tankPartName + 'Root'] = BigWorld.Model('objects/fake_model.model')
            compoundModel.node(TankPartNames.HULL).attach(fakeDict[tankPartName + 'Root'],
                                                          HullMat if 'hull' in tankPartName else deHullMat)
            if fakeMotorDict.get(tankPartName) not in tuple(fakeDict[tankPartName].motors):
                fakeMotorDict[tankPartName] = BigWorld.Servo(fakeDict[tankPartName + 'Root'].matrix)
                fakeDict[tankPartName].addMotor(fakeMotorDict[tankPartName])
            if fakeDict[tankPartName] not in tuple(BigWorld.models()):
                BigWorld.addModel(fakeDict[tankPartName])
        for idx, node in enumerate(nodeListNL):
            fakeDict[node] = BigWorld.Model('objects/fake_model.model')
            fakeDict[TankPartNames.CHASSIS].node('', nodeListML[idx]).attach(fakeDict[node])

        for idx, node in enumerate(nodeListNR):
            fakeDict[node] = BigWorld.Model('objects/fake_model.model')
            fakeDict[TankPartNames.CHASSIS].node('', nodeListMR[idx]).attach(fakeDict[node])

        for node in constNodesList:
            fakeDict[node] = BigWorld.Model('objects/fake_model.model')
            restoreMat = math_utils.createIdentityMatrix()
            transMat = None
            isChassis = False
            if sourcesDict[TankPartNames.HULL] is not None:
                transMat = nodeWatcher(sourcesDict[TankPartNames.HULL], node)
            if transMat is None and sourcesDict[TankPartNames.CHASSIS] is not None:
                transMat = nodeWatcher(sourcesDict[TankPartNames.CHASSIS], node)
                if transMat is None:
                    transMat = nodeWatcher(sourcesDict[TankPartNames.CHASSIS], node.replace('Up', ''))
                isChassis = True
            if transMat is None:
                print _config.ID + ': restore Matrix not found for node', node, 'in', vDesc.hull.models.undamaged
                print callPlace
            else:
                restoreMat.setTranslate(transMat.translation)
            fakeDict[TankPartNames.HULL if not isChassis else TankPartNames.CHASSIS].node('', restoreMat).attach(
                fakeDict[node])

        fakeDict[TankPartNames.GUN + 'Root'] = BigWorld.Model('objects/fake_model.model')
        compoundModel.node(TankPartNames.GUN).attach(fakeDict[TankPartNames.GUN + 'Root'])
        fakeDict[TankPartNames.GUN] = BigWorld.Model('objects/fake_model.model')
        if fakeMotorDict.get(TankPartNames.GUN) not in tuple(fakeDict[TankPartNames.GUN].motors):
            fakeMotorDict[TankPartNames.GUN] = BigWorld.Servo(fakeDict[TankPartNames.GUN + 'Root'].matrix)
            fakeDict[TankPartNames.GUN].addMotor(fakeMotorDict[TankPartNames.GUN])
        if fakeDict[TankPartNames.GUN] not in tuple(BigWorld.models()):
            BigWorld.addModel(fakeDict[TankPartNames.GUN])
        fakeDict[TankPartNames.TURRET] = BigWorld.Model('objects/fake_model.model')
        fakeDict[TankPartNames.TURRET + 'Root'] = BigWorld.Model('objects/fake_model.model')
        fakeDict[TankPartNames.TURRET + 'RootRoot'] = BigWorld.Model('objects/fake_model.model')
        hull_bbox_min, hull_bbox_max, _ = vDesc.hull.hitTester.bbox
        turret_pos_on_hull = vDesc.hull.turretPositions[0]
        turret_bbox_max = vDesc.turret.hitTester.bbox[1]
        gun_pos_on_turret = vDesc.turret.gunPosition
        gun_pos_on_hull = gun_pos_on_turret + turret_pos_on_hull
        gun_bbox_max = vDesc.gun.hitTester.bbox[1]
        if hull_bbox_max.y >= turret_pos_on_hull.y + turret_bbox_max.y:
            observer_pos = Math.Vector3(0, hull_bbox_max.y, 0)
            node = TankPartNames.HULL
        elif gun_pos_on_turret.y + gun_bbox_max.y >= turret_bbox_max.y:
            observer_pos = Math.Vector3(0, gun_bbox_max.y, 0)
            node = TankPartNames.GUN
        else:
            observer_pos = Math.Vector3(0, turret_bbox_max.y, 0)
            node = TankPartNames.TURRET
        mat = Math.Matrix()
        mat.setTranslate(observer_pos)
        compoundModel.node(node).attach(fakeDict[TankPartNames.TURRET + 'RootRoot'])
        if fakeMotorDict.get(TankPartNames.TURRET + 'Root') not in tuple(
                fakeDict[TankPartNames.TURRET + 'Root'].motors):
            fakeMotorDict[TankPartNames.TURRET + 'Root'] = BigWorld.Servo(
                fakeDict[TankPartNames.TURRET + 'RootRoot'].matrix)
            fakeDict[TankPartNames.TURRET + 'Root'].addMotor(fakeMotorDict[TankPartNames.TURRET + 'Root'])
        if fakeDict[TankPartNames.TURRET + 'Root'] not in tuple(BigWorld.models()):
            BigWorld.addModel(fakeDict[TankPartNames.TURRET + 'Root'])
        fakeDict[TankPartNames.TURRET + 'Root'].node('', mat).attach(fakeDict[TankPartNames.TURRET])

        hullLocalCenterY = (hull_bbox_min.y + hull_bbox_max.y) / 2.0
        hullLocalCenterZ = (hull_bbox_min.z + hull_bbox_max.z) / 2.0
        nodes = {'hullLocalPt1': Math.Vector3(0.0, hullLocalCenterY, hull_bbox_max.z),
                 'hullLocalPt2': Math.Vector3(0.0, hullLocalCenterY, hull_bbox_min.z),
                 'hullLocalPt3': Math.Vector3(hull_bbox_max.x, gun_pos_on_hull.y, hullLocalCenterZ),
                 'hullLocalPt4': Math.Vector3(hull_bbox_min.x, gun_pos_on_hull.y, hullLocalCenterZ),
                 'hullGunLocal': gun_pos_on_hull}
        for node in nodes:
            fakeDict[node] = BigWorld.Model('objects/fake_model.model')
            fakeDict[TankPartNames.HULL].node('', math_utils.createTranslationMatrix(nodes[node])).attach(fakeDict[node])

        lightDBDict.setdefault(vehicleID, {})
        for configDict in _config.configsDict.values():
            for name in sorted(configDict.keys()):
                try:
                    if name in ('enable', 'meta', 'attachToPlayer', 'attachToAlly', 'attachToEnemy'):
                        continue
                    confDict = configDict[name]
                    needToAttach = \
                        confDict['attachToPlayer'] and vehicleID == BigWorld.player().playerVehicleID or \
                        confDict['attachToEnemy'] and vehicle['team'] != BigWorld.player().team or \
                        confDict['attachToAlly'] and vehicleID != BigWorld.player().playerVehicleID and \
                        vehicle['team'] == BigWorld.player().team
                    if not needToAttach:
                        continue
                    nodeL = []
                    if '.' in name:
                        nodeL.append(confDict['place'])
                    elif confDict['place'] == 'leftFront':
                        nodeL.append(TankNodeNames.TRACK_LEFT_UP_FRONT)
                    elif confDict['place'] == 'rightFront':
                        nodeL.append(TankNodeNames.TRACK_RIGHT_UP_FRONT)
                    elif confDict['place'] == 'leftRear':
                        nodeL.append(TankNodeNames.TRACK_LEFT_UP_REAR)
                    elif confDict['place'] == 'rightRear':
                        nodeL.append(TankNodeNames.TRACK_RIGHT_UP_REAR)
                    elif confDict['place'] == 'hull':
                        nodeL.append(TankPartNames.HULL)
                    elif confDict['place'] == 'turret':
                        nodeL.append(TankPartNames.TURRET)
                    elif confDict['place'] == 'spot':
                        nodeL.extend([TankPartNames.TURRET, TankPartNames.GUN])
                        nodeL.extend(['hullLocalPt%s' % num for num in xrange(1, 5)])
                        nodeL.append('hullGunLocal')
                    elif 'wheels' in confDict['place']:
                        if 'left' in confDict['place']:
                            nodeL.extend(nodeListNL)
                        else:
                            nodeL.extend(nodeListNR)

                    nameTree = name.split('.')[:-1]
                    namesList = []
                    for curKey in lightDBDict[vehicleID].keys():
                        curTree = curKey.split('.')
                        if len(curTree) != len(nameTree) or any(
                                upperName not in curTree[depth] for depth, upperName in
                                enumerate(nameTree)):
                            continue
                        namesList.append(curKey + '.' + name.split('.')[-1])
                    if not namesList:
                        namesList = [name]
                    for fullName in namesList:
                        for node in nodeL:
                            curName = fullName + ':' + node
                            if 'model' not in confDict['type']:
                                if confDict['type'] == 'spotLight':
                                    LightSource = BigWorld.PySpotLight()
                                    LightSource.coneAngle = confDict['ca']
                                else:
                                    LightSource = BigWorld.PyOmniLight()
                                    if confDict['type'] != 'omniLight':
                                        LOG_ERROR('Unknown type of %s: %s. Set to omniLight' % (name, confDict['type']))
                                LightSource.innerRadius = confDict['innerRadius']
                                LightSource.outerRadius = confDict['outerRadius']
                                LightSource.castShadows = confDict['cs']
                                LightSource.multiplier = confDict['bright']
                                if isinstance(confDict['colour'][0], tuple):
                                    if confDict['type'] != 'spotLight':
                                        FrontLightShader = Math.Vector4Animation()
                                        FrontLightShader.duration = confDict['dur']
                                        FrontLightShader.keyframes = confDict['colour']
                                        LightSource.colorAnimator = FrontLightShader
                                    else:
                                        LightSource.colour = confDict['colour'][0][1]
                                else:
                                    LightSource.colour = confDict['colour']
                            else:
                                LightSource = BigWorld.Model(confDict['path'])
                            if '.' not in name:
                                if node in fakeDict:
                                    fakeNode = fakeDict[node].node('', computeTransform(confDict))
                            else:
                                if curName not in fakeDict:
                                    fakeDict[curName] = BigWorld.Model('objects/fake_model.model')
                                    lightDBDict[vehicleID][curName.rsplit('.', 1)[0]].node(node).attach(fakeDict[curName])
                                fakeNode = fakeDict[curName].node('', computeTransform(confDict))
                            if 'model' not in confDict['type']:
                                # noinspection PyUnboundLocalVariable
                                LightSource.source = fakeNode
                            elif not LightSource.attached:
                                fakeNode.attach(LightSource)
                            lightVisible(LightSource, _config.isLampsVisible and name in _config.modes['constant'])
                            lightDBDict[vehicleID][curName] = LightSource

                except StandardError:
                    traceback.print_exc()
                    print name
                    print callPlace
                    print vDesc.name

    except StandardError:
        traceback.print_exc()
        print callPlace


def lightVisible(obj, visible):
    if isinstance(obj, BigWorld.Model):
        obj.visible = visible
    elif visible and obj.multiplier <= 1:
        obj.multiplier *= 10000
    elif not visible and obj.multiplier > 1:
        obj.multiplier *= 0.0001


def lightsDetach(vehicleID):
    if vehicleID in lightDBDict:
        for confKey in lightDBDict[vehicleID]:
            if isinstance(lightDBDict[vehicleID][confKey], BigWorld.Model):
                lightDBDict[vehicleID][confKey].visible = False
            else:
                lightVisible(lightDBDict[vehicleID][confKey], False)
                lightDBDict[vehicleID][confKey].destroyLight()
                lightDBDict[vehicleID][confKey] = None


def lightsDestroy(vehicleID, callPlace=''):
    try:
        if vehicleID == BigWorld.player().playerVehicleID:
            print 'LampLights: Destroy at %s' % callPlace
        if vehicleID in lightDBDict:
            lightsDetach(vehicleID)
            del lightDBDict[vehicleID]
        if vehicleID in fakeMotorsDict:
            fakeMotorDict = fakeMotorsDict[vehicleID]
            for nodeName in fakeMotorDict:
                try:
                    BigWorld.delModel(fakesDict[vehicleID][nodeName])
                except ValueError:
                    traceback.print_exc()
                    print nodeName
                if fakeMotorDict[nodeName] in tuple(fakesDict[vehicleID][nodeName].motors):
                    fakesDict[vehicleID][nodeName].delMotor(fakeMotorDict[nodeName])

            del fakeMotorsDict[vehicleID]
        if vehicleID in fakesDict:
            del fakesDict[vehicleID]
    except StandardError:
        traceback.print_exc()
        print callPlace


statistic_mod = Analytics(_config.ID, _config.version, 'UA-76792179-2', _config.configsDict)
curSpeedsDict = {}


@overrideMethod(Vehicle, 'startVisual')
def new_startVisual(base, self):
    base(self)
    if self.isStarted and self.isAlive() and _config.data['enabled'] and _config.isLampsVisible:
        BigWorld.callback(0.1, partial(lightsCreate, self.id, 'Vehicle.startVisual'))


@overrideMethod(Vehicle, 'stopVisual')
def new_vehicle_onLeaveWorld(base, self, *args, **kwargs):
    if self.isStarted:
        lightsDestroy(self.id, 'Vehicle.stopVisual')
    base(self, *args, **kwargs)


@overrideMethod(PlayerAvatar, 'leaveArena')
def new_leaveArena(base, *a, **kw):
    for vehID in lightDBDict.keys():
        lightsDestroy(vehID, 'Avatar.leaveArena')
    base(*a, **kw)


@overrideMethod(CompoundAppearance, 'onVehicleHealthChanged')
def new_oVHC(base, self, *args, **kwargs):
    vehicle = self._CompoundAppearance__vehicle
    if not vehicle.isAlive():
        lightsDestroy(vehicle.id, 'oVHC_vehicle_not_isAlive')
    base(self, *args, **kwargs)


@overrideMethod(CompoundAppearance, '_periodicUpdate')
def new_periodicUpdate(base, self):
    base(self)
    if self._vehicle is None:
        return
    if not _config.data['enabled'] or not _config.isLampsVisible or not _config.isTickRequired:
        return
    vehicleID = self._vehicle.id
    if vehicleID not in lightDBDict:
        return
    curSpeeds = curSpeedsDict.setdefault(vehicleID, {})
    oldSpeed = curSpeeds.setdefault('curSpeed', 0.0)
    speedValue = self._CompoundAppearance__vehicle.filter.speedInfo.value
    curSpeed = round(speedValue[0], 1)
    curRSpeed = round(speedValue[1], 1)
    doVisible = {'back': curSpeed < 0,
                 'turn_left': curRSpeed != 0 and ((curRSpeed > 0) != (curSpeed >= 0)),
                 'turn_right': curRSpeed != 0 and ((curRSpeed > 0) == (curSpeed >= 0)),
                 'stop': abs(oldSpeed) - abs(curSpeed) > 0.6}
    lightDB = lightDBDict[vehicleID]
    for curKey in lightDB:
        lightInstance = lightDB[curKey]
        for modeName in doVisible:
            for confKey in _config.modes[modeName]:
                if confKey in curKey:
                    lightVisible(lightInstance, doVisible[modeName])

    curSpeeds['curSpeed'] = curSpeed
    curSpeeds['curRSpeed'] = curRSpeed


def spotToggle(vehicleID, lightIdx, status):
    if lightDBDict.get(vehicleID) is None:
        return
    nodes = [TankPartNames.TURRET, TankPartNames.GUN]
    nodes.extend(['hullLocalPt%s' % num for num in xrange(1, 5)])
    nodes.append('hullGunLocal')
    if _config.isLampsVisible:
        for confKey in _config.modes['spot']:
            for curKey in lightDBDict[vehicleID]:
                if confKey in curKey and nodes[lightIdx] in curKey:
                    lightVisible(lightDBDict[vehicleID][curKey], (
                        status
                        if not isinstance(lightDBDict[vehicleID][curKey], BigWorld.Model) or lightIdx not in (1, 6)
                        else False))


@overrideMethod(PlayerAvatar, 'targetFocus')
def new_targetFocus(base, self, entity):
    base(self, entity)
    if entity not in self._PlayerAvatar__vehicles:
        return
    if _config.isLampsVisible:
        for confKey in _config.modes['target']:
            for vehicleID in lightDBDict:
                for curKey in lightDBDict[vehicleID]:
                    if confKey in curKey:
                        lightVisible(lightDBDict[vehicleID][curKey], vehicleID == entity.id)


@overrideMethod(PlayerAvatar, 'targetBlur')
def new_targetBlur(base, self, prevEntity):
    base(self, prevEntity)
    if prevEntity not in self._PlayerAvatar__vehicles:
        return
    if _config.isLampsVisible:
        for confKey in _config.modes['target']:
            for vehicleID in lightDBDict:
                for curKey in lightDBDict[vehicleID]:
                    if confKey in curKey:
                        lightVisible(lightDBDict[vehicleID][curKey], False)
