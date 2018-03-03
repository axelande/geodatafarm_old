# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeoDataFarm
                                 A QGIS plugin
 This is a plugin that aims to determine the yield impact of different parameters
                              -------------------
        begin                : 2016-05-13
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Axel Andersson
        email                : axel.n.c.andersson@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# Initialize Qt resources from file resources.py
# Import the code for the dialog
#import pydevd
#pydevd.settrace('localhost', port=53100, stdoutToServer=True, stderrToServer=True)
import os
import os.path
import sys
sys.path.append(os.path.dirname(__file__))
from qgis.core import QgsMapLayerRegistry, QgsVectorLayer
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, Qt
from PyQt4.QtGui import QAction, QIcon, QMessageBox
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dock_widget and the subwidgets
from GeoDataFarm_dockwidget import GeoDataFarmDockWidget
from database_scripts.db import DB
from database_scripts.mean_analyse import Analyze
from import_data.handle_text_data import InputTextHandler
from database_scripts.create_new_farm import CreateFarm
from import_data.insert_input_to_db import InsertInputToDB
from import_data.handle_input_shp_data import InputShpHandler
from import_data.handle_db_file_data import DBFileHandler
from import_data.insert_harvest_to_db import InsertHarvestData
from database_scripts.table_managment import TableManagement
from support_scripts.create_layer import CreateLayer


# TODO: Known bugs:
# TODO: Add polygon while importing shapefiles
# TODO: Data till g?dning
# TODO: Different yields map, per crop, normalised over years.
# TODO: "planet labs" for satelite data
class GeoDataFarm:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'GeoDataFarm_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&GeoFarm')
        self.toolbar = self.iface.addToolBar(u'GeoDataFarm')
        self.toolbar.setObjectName(u'GeoDataFarm')

        #print "** INITIALIZING GeoDataFarm"

        self.pluginIsActive = False
        self.dock_widget = None
        self.items_in_table = [[None, ''], [None, ''], [None, '']]
        self.tables_in_db = [0, 0, 0]
        self.DB = None
        self.IH = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GeoDataFarm', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
        add_to_menu=True, add_to_toolbar=True, status_tip=None,
        whats_this=None, parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action


    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = ':/plugins/GeoDataFarm/img/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'GeoDataFarm'),
            callback=self.run,
            parent=self.iface.mainWindow())

    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dock_widget is closed"""
        self.dock_widget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        #print "** UNLOAD GeoDataFarm"

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&GeoFarm'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    #--------------------------------------------------------------------------
    def add_selected_tables(self):
        """Adds a layer for each "parameter" of all selected tables
        """
        tables = []
        for list_widget, schema in self.items_in_table:
            for item in list_widget:
                if item.checkState() == 2:
                    tables.append(str(item.text()))
        parameters = self.DB.get_indexes(', '.join("'" + str(e) + "'" for e in tables)[1:-1], False)
        for nr in range(len(parameters)):
            target_field = parameters[nr]['index_col']
            tbl_name = parameters[nr]['tbl_name']
            if 'field_row_id' in target_field:
                continue
            if parameters[nr]['schema'] == 'harvest':
                layer = self.DB.addPostGISLayer(tbl_name.lower(), 'pos', parameters[nr]['schema'], target_field.lower())
            else:
                layer = self.DB.addPostGISLayer(tbl_name.lower(), 'polygon', parameters[nr]['schema'], str(target_field.lower()))
            create_layer = CreateLayer(self.DB)
            create_layer.create_layer_style(layer, target_field, tbl_name.lower(), parameters[nr]['schema'])
            QgsMapLayerRegistry.instance().addMapLayer(layer)

    def reload_layer(self):
        create_layer = CreateLayer(self.DB, self.dock_widget)
        create_layer.repaint_layer()

    def update_table_list(self):
        """Update the list of tables in the docket widget"""
        self.DB = DB(self.dock_widget, path=self.plugin_dir)
        connected = self.DB.get_conn()
        if not connected:
            QMessageBox.information(None, "Error:", self.tr('No farm is created, please create a farm to continue'))
            return
        lw_list = [[self.dock_widget.LWActivityTable, 'activity'],
                   [self.dock_widget.LWHarvestTable, 'harvest'],
                   [self.dock_widget.LWSoilTable, 'soil']]
        for i, (lw, schema) in enumerate(lw_list):
            table_names = self.DB.get_tables_in_db(schema)
            if self.tables_in_db[i] != 0:
                model = lw.model()
                for item in self.items_in_table[i][0]:
                    q_index = lw.indexFromItem(item)
                    model.removeRow(q_index.row())
            self.tables_in_db[i] = 0
            for name in table_names:
                if name[0] in ["spatial_ref_sys", "pointcloud_formats",
                               "temp_polygon"]:
                    continue
                item_name = str(name[0])
                _name = QtGui.QApplication.translate("qadashboard", item_name, None)
                item = QtGui.QListWidgetItem(_name, lw)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                self.tables_in_db[i] += 1
            self.items_in_table[i][0] = lw.findItems('', QtCore.Qt.MatchContains)
            self.items_in_table[i][1] = schema

    def reload_range(self):
        cb = self.dock_widget.mMapLayerComboBox
        layer = cb.currentLayer()
        if layer is not None:
            try:
                lv = layer.rendererV2().ranges()[0].lowerValue()
                hv = layer.rendererV2().ranges()[-1].upperValue()
                nbr_cat = len(layer.rendererV2().ranges())
                self.dock_widget.LEMinColor.setText(str(lv))
                self.dock_widget.LEMaxColor.setText(str(hv))
                self.dock_widget.LEMaxNbrColor.setText(str(nbr_cat))
            except AttributeError:
                pass

    def run_analyse(self):
        """Gathers the "in parameters" and start the analyse session"""
        names = []
        harvest_file = False
        input_file = False
        lw_list = [[self.dock_widget.LWActivityTable, 'activity'],
                   [self.dock_widget.LWHarvestTable, 'harvest'],
                   [self.dock_widget.LWSoilTable, 'soil']]
        for i, (lw, schema) in enumerate(lw_list):
            for item in self.items_in_table[i][0]:
                if item.checkState() == 2:
                    if schema == 'harvest':
                        harvest_file = True
                    if schema == 'activity' or schema == 'soil':
                        input_file = True
                    names.append(item.text().encode("ascii"))
        if harvest_file and input_file:
            Analyze(names, self).add_input()
        else:
            QMessageBox.information(None, "Error:", self.tr('You need to have at least one input and one harvest data set selected.'))

    def clicked_input(self):
        """Connects the docked widget with the correct InputHandler script and 
        starts the input widget"""
        if self.dock_widget.CBFileType.currentText() == 'Text file (.csv; .txt)':
            self.IH = InputTextHandler(self.iface, self)
            self.IH.run()
        elif self.dock_widget.CBFileType.currentText() == 'Databasefile (.db)':
            self.IH = DBFileHandler(self.iface, self.dock_widget)
            self.IH.start_up()
        elif self.dock_widget.CBFileType.currentText() == 'Shape file (.shp)':
            try:
                feature = self.df.getFeatures().next()
                polygon = feature.geometry().asPolygon()[0]
            except:
                polygon = None
            self.ShpHandler = InputShpHandler(self.iface, self, polygon)
            self.ShpHandler.add_input()

    def _q_replace_db_data(self, tbl=None):
        schema = self.dock_widget.CBDataType.currentText()
        tables_in_db = self.DB.get_tables_in_db(schema=schema)
        if tbl is not None:
            tbl_name = tbl
        else:
            tbl_name = str(self.IH.file_name)
        tbls = []
        for row in tables_in_db:
            tbls.append(str(row[0]))
        if tbl_name in tbls:
            qm = QMessageBox()
            ret = qm.question(None, 'Message',
                              self.tr("The name of the data set already exist in your database, would you like to replace it?"),
                              qm.Yes, qm.No)
            if ret == qm.No:
                return False
            else:
                self.DB.execute_sql(
                    "DROP TABLE {schema}.{tbl}".format(schema=schema,
                                                       tbl=tbl_name))
                return True
        else:
            return True

    def clicked_input2(self):
        """Connects the docked widget with the InserInputInDB script and starts
        the inserting of data into the database"""
        if self._q_replace_db_data():
            schema = self.dock_widget.CBDataType.currentText()
            try:
                feature = self.df.getFeatures().next()
                polygon = feature.geometry().asPolygon()[0]
            except:
                polygon = None
            try:
                QgsMapLayerRegistry.instance().removeMapLayer(self.df)
            except:
                pass
            if schema == 'harvest':
                obj = InsertHarvestData(self.IH, self.iface, self.dock_widget,
                                  polygon, self.DB, self.tr)
                obj.insert_to_db()
            else:
                iitdb = InsertInputToDB(self.IH, self.iface, self.dock_widget, polygon, self.DB)
                iitdb.import_data_to_db(schema)

    def clicked_define_field(self):
        """Creates an empty polygon that's define a field"""
        self.df = QgsVectorLayer("Polygon?crs=epsg:4326", "temporary_points", "memory")
        self.df.startEditing()
        QgsMapLayerRegistry.instance().addMapLayer(self.df)

    def tbl_mgmt(self):
        """Open the table manager widget"""
        tabel_mgmt = TableManagement(self)
        tabel_mgmt.run()

    def clicked_create_farm(self):
        """Connects the docked widget with the CreateFarm script and starts
        the create_farm widget"""
        create_farm = CreateFarm(self.iface, self)
        create_farm.run()

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            #print "** STARTING GeoDataFarm"

            # dock_widget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dock_widget is None:
                # Create the dock_widget (after translation) and keep reference
                self.dock_widget = GeoDataFarmDockWidget()
            self.update_table_list()
            self.dock_widget.PBAddFile.clicked.connect(self.clicked_input)
            self.dock_widget.PBAddFieldToDB.clicked.connect(self.clicked_input2)
            self.dock_widget.PBReloadLayer.clicked.connect(self.reload_layer)
            self.dock_widget.PBAddNewFarm.clicked.connect(self.clicked_create_farm)
            self.dock_widget.PBDefineField.clicked.connect(self.clicked_define_field)
            self.dock_widget.PBUpdateLists.clicked.connect(self.update_table_list)
            self.dock_widget.PBEditTables.clicked.connect(self.tbl_mgmt)
            self.dock_widget.PBRunAnalyses.clicked.connect(self.run_analyse)
            self.dock_widget.PBAdd2Canvas.clicked.connect(self.add_selected_tables)
            #self.dock_widget.pb_add_irrigation.clicked.connect(self.import_irrigation)
            try:
                self.reload_range()
            except:
                pass
            self.dock_widget.mMapLayerComboBox.currentIndexChanged.connect(self.reload_range)
            # show the dock_widget
            # connect to provide cleanup on closing of dock_widget
            self.dock_widget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
            self.dock_widget.show()
