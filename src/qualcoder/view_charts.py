# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

from copy import copy, deepcopy
import logging
import os
import pandas as pd
import plotly.express as px
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from collections import defaultdict
import plotly.graph_objects as go
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QDialog
from .simple_wordcloud import Wordcloud
from plotly.colors import qualitative
import colorsys
from .GUI.ui_dialog_charts import Ui_DialogCharts

from .helpers import ExportDirectoryPathDialog, Message
from .report_attributes import DialogSelectAttributeParameters

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)
pal_corporate = [
            "#97bf13", "#688816", "#3f570a", "#838383",
            "#00616f", "#01b3c4", "#00a182"
        ]
pal_colorblind = ['#0072B2', '#E69F00', '#009E73', '#F0E442',
                        '#56B4E9', '#D55E00', '#CC79A7', '#000000']

class ViewCharts(QDialog):
    """ Dialog to view various charts of codes and categories.
    """

    app = None
    conn = None
    settings = None
    categories = []
    codes = []
    files = []
    cases = []
    attributes = []  # For charts of attributes
    attribute_file_ids = []  # For filtering based on attribute selection
    attributes_msg = ""  # Tooltip msg for filtering based on attribute selection
    attribute_case_ids_and_names = []  # Used for Case heatmaps based on attribute selection

    def __init__(self, app):
        """ Set up the dialog. """

        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        self.attribute_file_ids = []
        self.attributes_msg = ""
        # Set up the user interface from Designer.
        self.ui = Ui_DialogCharts()
        self.ui.setupUi(self)
        integers = QtGui.QIntValidator()
        self.ui.lineEdit_filter.setValidator(integers)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.pushButton_attributes.pressed.connect(self.select_attributes)
        # Get coder names from all tables
        sql = "select owner from  code_image union select owner from code_text union select owner from code_av "
        sql += " union select owner from cases union select owner from journal union select owner from attribute "
        sql += "union select owner from source union select owner from annotation union select owner from code_name "
        sql += "union select owner from code_cat"
        coders = [""]
        cur = self.app.conn.cursor()
        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            if row[0] != "":
                coders.append(row[0])
        self.ui.comboBox_coders.addItems(coders)

        self.attributes = []
        cur.execute("select name, ifnull(memo,''), caseOrFile, valuetype from attribute_type")
        result = cur.fetchall()
        self.attributes = []
        keys = 'name', 'memo', 'caseOrFile', 'valuetype'
        for row in result:
            self.attributes.append(dict(zip(keys, row)))
        self.fill_combobox_attributes()
        self.ui.radioButton_file.clicked.connect(self.fill_combobox_attributes)
        self.ui.radioButton_case.clicked.connect(self.fill_combobox_attributes)
        self.ui.radioButton_default.setChecked(True)
        self.ui.radioButton_color_blind.clicked.connect(self.update_color_palette)
        self.ui.radioButton_default.clicked.connect(self.update_color_palette)
        self.ui.radioButton_corporate.clicked.connect(self.update_color_palette)
        self.ui.comboBox_pie_charts.currentIndexChanged.connect(self.show_pie_chart)
        self.ui.comboBox_bar_charts.currentIndexChanged.connect(self.show_bar_chart)
        self.selected_color_palette = None
        self.update_color_palette()
        self.files = self.app.get_filenames()
        files_combobox_list = [""]
        for f in self.files:
            files_combobox_list.append(f['name'])
        self.ui.comboBox_file.addItems(files_combobox_list)
        self.cases = self.app.get_casenames()
        cases_combobox_list = [""]
        for f in self.cases:
            cases_combobox_list.append(f['name'])
        self.ui.comboBox_case.addItems(cases_combobox_list)
        self.ui.comboBox_case.currentIndexChanged.connect(self.clear_combobox_files)
        self.ui.comboBox_file.currentIndexChanged.connect(self.clear_combobox_cases)
        self.get_selected_categories_and_codes()
        pie_combobox_list = ['', _('Label frequency'),
                             _('Label by characters'),
                             #_('Label by image area'),
                             #_('Label by audio/video segments'),
                             ]
        self.ui.comboBox_pie_charts.addItems(pie_combobox_list)
        #self.ui.comboBox_sunburst_charts.currentIndexChanged.connect(self.show_hierarchy_chart)
        sunburst_combobox_list = ['',# _('Label frequency sunburst'),
                                  #_('Code frequency treemap'),
                                  #_('Label by characters sunburst'),
                                  #_('Code by characters treemap'),
                                  #_('Label by image area sunburst'),
                                  #_('Code by image area treemap'),
                                 # _('Label by A/V sunburst'),
                                  #_('Code by A/V treemap')
                                  ]
        #self.ui.comboBox_sunburst_charts.addItems(sunburst_combobox_list)
        self.ui.comboBox_bar_charts.currentIndexChanged.connect(self.show_bar_chart)
        bar_combobox_list = ['', _('Label frequency'),
                             _('Label by characters'),
                             #_('Label by image area'),
                             #_('Label by audio/video segments')
                             ]
        self.ui.comboBox_bar_charts.addItems(bar_combobox_list)
        categories_combobox_list = [""]
        for c in self.categories:
            categories_combobox_list.append(c['name'])
        self.ui.comboBox_category.addItems(categories_combobox_list)
        # QIntValidator does not use upper limits, it is based on number of digits entered. eg 99 possible
        self.ui.lineEdit_count_limiter.setValidator(QtGui.QIntValidator(0, 50))
        self.ui.lineEdit_count_limiter.setText("0")

        self.ui.label_word_clouds.setToolTip(_("Word cloud made from coded text segments"))
        wordcloud_backgrounds = ['Black', 'White']  # Do not translate!
        self.ui.comboBox_wordcloud_background.addItems(wordcloud_backgrounds)
        wordcloud_foregrounds = ["white", "grey", "black", 'yellow', 'green', "red", "cyan", "magenta", "deepskyblue",
                                 "indigo", "lightcoral", "olive", "tan",
                                 "greys", "greens", "oranges", "pinks", "reds", "yellows", "blues",
                                 "blue to yellow", "blue to orange", "blue to red", "blue to aqua", "grey to red",
                                 "black to pink", "orange to purple", "salmon to aqua", "green to blue",
                                 "yellow to green", "aqua to pink", "river nights", "random"
                                 ]
        self.ui.comboBox_wordcloud_foreground.addItems(wordcloud_foregrounds)
        wordcloud_ngram_options = ["1", "2", "3", "4"]
        self.ui.comboBox_ngrams.addItems(wordcloud_ngram_options)
        # QIntValidator does not use upper limits, it is based on number of digits entered. eg 999 possible
        self.ui.lineEdit_max_words.setValidator(QtGui.QIntValidator(50, 500))
        self.ui.lineEdit_max_words.setText("200")
        # QIntValidator does not use upper limits, it is based on number of digits entered. eg 9999 possible
        self.ui.lineEdit_height.setValidator(QtGui.QIntValidator(100, 2000))
        self.ui.lineEdit_width.setText("800")
        self.ui.lineEdit_width.setValidator(QtGui.QIntValidator(100, 2000))
        self.ui.lineEdit_height.setText("600")
        # Make the icon larger by setting icon size on the button
        icon = qta.icon('mdi6.play', options=[{'scale_factor': 2}])
        self.ui.pushButton_wordcloud.setIcon(icon)
        self.ui.pushButton_wordcloud.setIconSize(QtCore.QSize(28, 28))  # Adjust size as needed
        self.ui.pushButton_wordcloud.pressed.connect(self.show_word_cloud)

        # Attributes comboboxes. Initial radio button checked is Files
        self.ui.comboBox_char_attributes.currentIndexChanged.connect(self.character_attribute_charts)
        self.ui.comboBox_num_attributes.currentIndexChanged.connect(self.numeric_attribute_charts)

        # Heatmaps
        heatmap_combobox_list = ["", "File", "Case"]
        self.ui.comboBox_heatmap.addItems(heatmap_combobox_list)
        self.ui.comboBox_heatmap.currentIndexChanged.connect(self.make_heatmap)


    def get_color_palette(self):
        # Check if the Colorblind radio button is checked
        if self.ui.radioButton_color_blind.isChecked():
            return pal_colorblind  # Colorblind-friendly palette
        
        # Check if the Corporate radio button is checked
        elif self.ui.radioButton_corporate.isChecked():
            return pal_corporate  # Corporate palette
        
        # Default: return None, which means the chart will use its default colors
        else:
            return None  # Default palette (visualization's built-in color scheme)

    def update_chart(self):
        """ This function will be called when the chart type is selected (from combo box). """
        
        # Get the selected color palette based on the radio button selection
        color_palette = self.get_color_palette()
        

        # Store the selected color palette in an instance variable
        self.selected_color_palette = color_palette  # Store it so it can be used when updating the chart
        self.show_pie_chart()  # Call function to update the chart based on the combo box selection
        self.show_bar_chart()

    def update_color_palette(self):
        """ This function will be called when any radio button is toggled. """
        # Get the selected color palette based on the radio button selection
        color_palette = self.get_color_palette()

        # Store the selected color palette (do not update the chart yet)
        self.selected_color_palette = color_palette
        print("Selected color palette:", self.selected_color_palette)
    
    # DATA FILTERS SECTION
    def select_attributes(self):
        """ Select files based on attribute selections using DialogSecectAttributeParameters.
        Attribute selection results are a list of:

        DialogSelectAttributeParameters returns lists for each parameter selected of:
        attribute name, file or case, character or numeric, operator, list of one or two comparator values
        two comparator values are used with the 'between' operator
        ['source', 'file', 'character', '==', ["'interview'"]]
        ['case name', 'case', 'character', '==', ["'ID1'"]]

        [0] boolean or OR boolean and
        [1] ...[n] each select attribute
        [['BOOLEAN_OR'], ['Age', 'case', 'numeric', '>', ['10']], ['source', 'file', 'character', '=', ["'internal'"]]]
        Each selected attribute contains:
        [0] attribute name,
        [1] case or file
        [2] attribute type: character, numeric
        [3] modifier: > < == != like between
        [4] comparison value as list, one item or two items for between

        sqls are NOT parameterised.
        Results from multiple parameters are intersected, an AND boolean function.
        Results stored in attribute_file_ids as list of file_id integers
        """

        self.attribute_case_ids = []  # TODO unsure here, Not used yet
        self.attribute_file_ids = []
        self.attributes_msg = ""
        ui = DialogSelectAttributeParameters(self.app)
        # ui.fill_parameters(self.attributes)
        ok = ui.exec()
        if not ok:
            self.ui.pushButton_attributes.setToolTip("")
            return
        # Run a series of sql based on each selected attribute
        # Apply a set to the resulting ids to determine the final list of ids
        # use the methods in the report_attributes.py
        # using file and case parameters and selected 'and' or 'or'
        self.attribute_file_ids = ui.result_file_ids
        self.attributes_msg = ui.tooltip_msg
        self.ui.pushButton_attributes.setToolTip(self.attributes_msg)

    def clear_combobox_files(self):
        """ Clear file selection if a case is selected.
        Clear any attributes selected.
        Called on combobox_case index change. """
        self.ui.comboBox_file.blockSignals(True)
        self.ui.comboBox_file.setCurrentIndex(0)
        self.ui.comboBox_file.blockSignals(False)
        self.attribute_file_ids = []
        self.attributes_msg = ""
        self.ui.pushButton_attributes.setToolTip("")

    def clear_combobox_cases(self):
        """ Clear case selection if a file is selected.
        Clear any attributes selected.
        Called on combobox_file index change. """

        self.ui.comboBox_case.blockSignals(True)
        self.ui.comboBox_case.setCurrentIndex(0)
        self.ui.comboBox_case.blockSignals(False)
        self.attribute_file_ids = []
        self.attributes_msg = ""
        self.ui.pushButton_attributes.setToolTip("")

    def get_file_ids(self):
        """ Get file ids based on file selection or case selection.
        Also returns attribute-selected file ids.
        Called by: pie, bar, hierarchy charts
        return two String values:
            attributes, case or file name;
            sql string of '' or file_ids comma separated as in (,,,) or =id
        """

        if self.attribute_file_ids:
            file_ids = ""
            for id_ in self.attribute_file_ids:
                file_ids += "," + str(id_)
            return _("Attributes: ") + self.attributes_msg + " ", f" in ({file_ids[1:]})"

        file_name = self.ui.comboBox_file.currentText()
        case_name = self.ui.comboBox_case.currentText()
        if file_name == "" and case_name == "":
            return "", ""
        if file_name != "":
            for f in self.files:
                if f['name'] == file_name:
                    return _("File: ") + file_name + " ", f"={f['id']}"
        case_id = -1
        for c in self.cases:
            if c['name'] == case_name:
                case_id = c['id']
                break
        cur = self.app.conn.cursor()
        sql = "select distinct fid from case_text where caseid=?"
        cur.execute(sql, [case_id, ])
        res = cur.fetchall()
        file_ids = ""
        for r in res:
            file_ids += "," + str(r[0])
        if file_ids == "":
            return "", ""
        return _("Case: ") + case_name + " ", f" in ({file_ids[1:]})"

    def get_selected_categories_and_codes(self):
        """ The base state contains all categories and codes.
        A selected category, via combo box selection, restricts the categories and codes.
        """

        self.codes, self.categories = self.app.get_codes_categories()
        # Extra keys for hierarchy charts
        for code in self.codes:
            code['count'] = 0
            code['parentname'] = ""
        for cat in self.categories:
            cat['count'] = 0
            cat['parentname'] = ""

        node = self.ui.comboBox_category.currentText()
        if node == "":
            return
        for category in self.categories:
            if category['name'] == node:
                node = category
                node['supercatid'] = None
                break
        """ Create a list of this category (node) and all its category children.
        Note, maximum depth of 100. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while self.categories != [] and new_model_changed and i < 100:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in self.categories:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
            for n in append_list:
                selected_categories.append(n)
                self.categories.remove(n)
                new_model_changed = True
            i += 1
        self.categories = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in self.categories:
            for code in self.codes:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        self.codes = selected_codes

    # CODING CHARTS SECTION
    def owner_and_subtitle_helper(self):
        """ Create initial subtitle and get owner
         return:
            String owner
            String subtitle of category selected
         """

        subtitle = "<br><sup>"
        owner = self.ui.comboBox_coders.currentText()
        if owner == "":
            owner = '%'
        else:
            subtitle += _("Coder: ") + owner + " "
        if self.ui.comboBox_category.currentText() != "":
            subtitle += _("Category: ") + self.ui.comboBox_category.currentText()
        return owner, subtitle

    def helper_export_html(self, fig):
        """ Export chart. """

        if self.ui.checkBox_export_html.isChecked():
            e = ExportDirectoryPathDialog(self.app, "Chart.html")
            filepath = e.filepath
            if filepath is None:
                return
            fig.write_html(filepath)

    def show_word_cloud(self):
        """ Show word cloud.
         Can be by file and/or by category. """

        title = _('Word cloud')
        owner, subtitle = self.owner_and_subtitle_helper()
        self.get_selected_categories_and_codes()
        cur = self.app.conn.cursor()
        values = []
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        for c in self.codes:
            sql = "select seltext from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select seltext from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchone()
            if res_text:
                values.append(res_text[0])
        # Create image
        text = " ".join(values)
        background = self.ui.comboBox_wordcloud_background.currentText()
        foreground = self.ui.comboBox_wordcloud_foreground.currentText()
        try:
            width = int(self.ui.lineEdit_width.text())
        except ValueError:
            width = 800
            self.ui.lineEdit_width.setText("800")
        try:
            height = int(self.ui.lineEdit_height.text())
        except ValueError:
            height = 600
            self.ui.lineEdit_height.setText("600")
        try:
            max_words = int(self.ui.lineEdit_max_words.text())
        except ValueError:
            max_words = 200
            self.ui.lineEdit_max_words.setText("200")
        reverse_colors = self.ui.checkBox_reverse_range.isChecked()
        ngrams = int( self.ui.comboBox_ngrams.currentText())
        Wordcloud(self.app, text, width=width, height=height, max_words=max_words, background_color=background,
                  text_color=foreground, reverse_colors=reverse_colors, ngrams=ngrams)

    def codes_of_category_helper(self, category_name):
        """ Get child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.

        param: node : Dictionary of category

        return: child_names : List
        """

        if category_name['cid'] is not None:
            return []
        child_names = []
        codes, categories = self.app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in codes:
            for cat in categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [category_name]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in categories:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for n in append_list:
                selected_categories.append(n)
                categories.remove(n)
                new_model_changed = True
            i += 1
        categories = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in categories:
            for code in codes:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        codes = selected_codes
        for c in codes:
            child_names.append(c['name'])
        return child_names

    def show_bar_chart(self):
        """ https://www.tutorialspoint.com/plotly/plotly_bar_and_pie_chart.htm
        Index numbering matches order of options, set up in init
        """

        chart_type_index = self.ui.comboBox_bar_charts.currentIndex()
        if chart_type_index < 1:
            return
        color_palette = self.selected_color_palette

        print("Color palette in update_selected_chart:", color_palette)

        self.get_selected_categories_and_codes()
        if chart_type_index == 1:  # Code frequency
            self.barchart_code_frequency_new(color_palette)
        if chart_type_index == 2:  # Code by characters
            self.barchart_code_volume_by_characters_new(color_palette)
        if chart_type_index == 3:  # Code by image area
            self.barchart_code_volume_by_area()
        if chart_type_index == 4:  # Code by audio/video segments
            self.barchart_code_volume_by_segments()
        self.ui.comboBox_bar_charts.setCurrentIndex(0)
    
    def barchart_code_frequency_new(self, color_palette=None):
        """Counts per code with palette toggles: Normal/Stacked × Default/Corporate/Color-blind."""
        title = _('Label count - text, images and Audio/Video')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()

        labels, text_counts, image_counts, av_counts = [], [], [], []

        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name

        # --- collect counts per code for Text / Image / A/V ---
        for c in self.codes:
            # Text
            sql = "select count(cid) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchone()

            # Image
            sql = "select count(cid) from code_image where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_image where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_image = cur.fetchone()

            # A/V
            sql = "select count(cid) from code_av where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_av where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_av = cur.fetchone()

            labels.append(c['name'])
            text_counts.append((res_text[0] or 0))
            image_counts.append((res_image[0] or 0))
            av_counts.append((res_av[0] or 0))

        # --- dataframe + cutoff filter based on TOTAL (like your original) ---
        df = pd.DataFrame({
            'Label names': labels,
            'Text': text_counts,
            'Image': image_counts,
            'A/V': av_counts
        })
        df['Total'] = df[['Text', 'Image', 'A/V']].sum(axis=1)

        df = df[df['Total'] > 0]
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            df = df[df['Total'] >= int(cutoff)]
            subtitle += _(" Values") + " >= " + cutoff

        if df.empty:
            self.ui.textEdit.append(_("No data to display."))
            return

        df = df.sort_values('Total', ascending=False)

        # Use the helper function to get the selected color palette (Default, Colorblind, or Corporate)
        if color_palette is None:
            color_palette = self.get_color_palette()

        # --- build traces: 1 Total (for Normal), plus 3 components (for Stacked) ---
        # For stacked, use the same color order for each series
        total_trace = go.Bar(
            y=df['Label names'],
            x=df['Total'],
            name=_('Total'),
            orientation='h',
            text=df['Total'],
            textposition='auto',
            marker=dict(color=color_palette)  # Apply selected color palette here
        )
        text_trace = go.Bar(
            y=df['Label names'],
            x=df['Text'],
            name=_('Text'),
            orientation='h',
            text=df['Text'],
            textposition='auto',
            marker=dict(color=color_palette)
        )
        image_trace = go.Bar(
            y=df['Label names'],
            x=df['Image'],
            name=_('Image'),
            orientation='h',
            text=df['Image'],
            textposition='auto',
            marker=dict(color=color_palette)
        )
        av_trace = go.Bar(
            y=df['Label names'],
            x=df['A/V'],
            name=_('Audio/Video'),
            orientation='h',
            text=df['A/V'],
            textposition='auto',
            marker=dict(color=color_palette)
        )

        fig = go.Figure(data=[total_trace, text_trace, image_trace, av_trace])

        fig.update_traces(marker_line_width=0.5, marker_line_color='white')

        # --- Visibility masks and buttons for Normal vs Stacked ---
        vis_normal = [True, False, False, False]  # Show Normal view
        vis_stacked = [False, True, True, True]  # Show Stacked view

        # Start in Normal view
        for i, v in enumerate(vis_normal):
            fig.data[i].visible = v

        fig.update_layout(
            title={'text': f"{title}{subtitle}", 'x': 0.5, 'xanchor': 'center'},
            template='seaborn',
            barmode='group',
            bargap=0.2,
            height=600,
            margin=dict(l=140, r=40, t=90, b=130),
            xaxis_title=_('Count'),
            yaxis_title=_('Label names'),
            legend_title=_('Series'),
            updatemenus=[dict(
                type='buttons',
                showactive=True,
                active=0,
                direction='right',
                x=0.5, xanchor='center',
                y=-0.12, yanchor='top',
                bgcolor='rgba(245,245,245,0.98)',
                bordercolor='#d0d0d0',
                borderwidth=1,
                pad={'l': 10, 'r': 10, 't': 6, 'b': 6},
                buttons=[
                    dict(
                        label=_('Normal'),
                        method='update',
                        args=[{'visible': vis_normal}, {'barmode': 'group', 'legend_title_text': _('Series')}]
                    ),
                    dict(
                        label=_('Stacked'),
                        method='update',
                        args=[{'visible': vis_stacked}, {'barmode': 'stack', 'legend_title_text': _('Series')}]
                    ),
                ]
            )],
        )

        # Soft grid + subtle border
        fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.08)', zeroline=False)
        fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.06)')
        fig.add_shape(
            type='rect', xref='paper', yref='paper',
            x0=0, y0=0, x1=1, y1=1,
            line=dict(color='#e5e7eb', width=1),
            fillcolor='rgba(0,0,0,0)',
            layer='below'
        )

        fig.show()
        self.helper_export_html(fig)

    def barchart_code_volume_by_characters_new(self, color_palette=None):
        TOP_N_FILES = 5     # top files to show as separate stacks
        TOP_N_OWNERS = 5    # top coders to show as separate stacks

        title = _('Label text by character count')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()

        label_list, totals, per_label_file, per_label_owner = [], [], [], []
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name:
            subtitle += case_file_name

        file_name_cache = {}

        # --- Collect totals, per-file, and per-owner data ---
        for c in self.codes:
            # Total chars per label (respects owner filter)
            sql_total = "select sum(pos1 - pos0) from code_text where cid=? and owner like ?"
            if file_ids:
                sql_total += " and fid" + file_ids
            cur.execute(sql_total, [c['cid'], owner])
            total_chars = (cur.fetchone()[0] or 0)

            # Per-file breakdown
            sql_pf = "select fid, sum(pos1 - pos0) from code_text where cid=? and owner like ?"
            if file_ids:
                sql_pf += " and fid" + file_ids
            sql_pf += " group by fid"
            cur.execute(sql_pf, [c['cid'], owner])
            rows_file = cur.fetchall() or []
            filedict = {}
            for fid, s in rows_file:
                if fid is None:
                    continue
                val = (s or 0)
                if fid not in file_name_cache:
                    try:
                        cur2 = self.app.conn.cursor()
                        cur2.execute("select name from source where id=?", [fid])
                        nm = cur2.fetchone()
                        file_name_cache[fid] = nm[0] if nm and nm[0] else f"File {fid}"
                    except Exception:
                        file_name_cache[fid] = f"File {fid}"
                fname = file_name_cache[fid]
                filedict[fname] = filedict.get(fname, 0) + val

            # Per-owner breakdown
            sql_po = "select owner, sum(pos1 - pos0) from code_text where cid=?"
            if file_ids:
                sql_po += " and fid" + file_ids
            sql_po += " group by owner"
            cur.execute(sql_po, [c['cid']])
            rows_owner = cur.fetchall() or []
            ownerdict = {}
            for own, s in rows_owner:
                key = own if (own and str(own).strip() != "") else _("(Unassigned)")
                ownerdict[key] = ownerdict.get(key, 0) + (s or 0)

            label_list.append(c['name'])
            totals.append(total_chars)
            per_label_file.append(filedict)
            per_label_owner.append(ownerdict)

        # --- DataFrame of totals + cutoff filter ---
        df_total = pd.DataFrame({'Label names': label_list, 'Total': totals})
        if self.ui.lineEdit_filter.text():
            try:
                thr = int(self.ui.lineEdit_filter.text())
                df_total = df_total[df_total['Total'] >= thr]
                subtitle += _(" Values ≥ ") + str(thr)
            except ValueError:
                pass
        df_total = df_total[df_total['Total'] > 0]
        if df_total.empty:
            self.ui.textEdit.append(_("No data to display."))
            return
        df_total = df_total.sort_values('Total', ascending=False).reset_index(drop=True)

        # Order dicts to match sorted labels
        label_to_files = dict(zip(label_list, per_label_file))
        label_to_owners = dict(zip(label_list, per_label_owner))
        ordered_labels = df_total['Label names'].tolist()

        # --- Stack by File ---
        from collections import defaultdict
        global_file_sums = defaultdict(int)
        for lab in ordered_labels:
            for fname, val in label_to_files.get(lab, {}).items():
                global_file_sums[fname] += val
        top_files = [fname for fname, _ in sorted(global_file_sums.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N_FILES]]

        stack_file_rows = []
        file_has_other = False
        for lab in ordered_labels:
            row = {'Label names': lab}
            fdict = label_to_files.get(lab, {})
            other_sum = 0
            for fname in top_files:
                row[fname] = fdict.get(fname, 0)
            for fname, val in fdict.items():
                if fname not in top_files:
                    other_sum += val
            if other_sum > 0:
                row['Other (files)'] = other_sum
                file_has_other = True
            stack_file_rows.append(row)
        df_stack_file = pd.DataFrame(stack_file_rows).fillna(0)
        file_cols = top_files + (['Other (files)'] if file_has_other else [])

        # --- Stack by Coder ---
        global_owner_sums = defaultdict(int)
        for lab in ordered_labels:
            for own, val in label_to_owners.get(lab, {}).items():
                global_owner_sums[own] += val
        top_owners = [own for own, _ in sorted(global_owner_sums.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N_OWNERS]]

        stack_owner_rows = []
        owner_has_other = False
        for lab in ordered_labels:
            row = {'Label names': lab}
            odict = label_to_owners.get(lab, {})
            other_sum = 0
            for own in top_owners:
                row[own] = odict.get(own, 0)
            for own, val in odict.items():
                if own not in top_owners:
                    other_sum += val
            if other_sum > 0:
                row['Other (coders)'] = other_sum
                owner_has_other = True
            stack_owner_rows.append(row)
        df_stack_owner = pd.DataFrame(stack_owner_rows).fillna(0)
        owner_cols = top_owners + (['Other (coders)'] if owner_has_other else [])

        # --- Color handling (radio buttons) ---
        if color_palette is None:
            color_palette = self.get_color_palette()

        # Assign solid colors (no cycling)
        total_color = color_palette[0] if color_palette else None
        file_colors = color_palette[:len(file_cols)] if color_palette else [None]*len(file_cols)
        owner_colors = color_palette[:len(owner_cols)] if color_palette else [None]*len(owner_cols)

        # --- Build figure ---
        import plotly.graph_objects as go
        fig = go.Figure()

        # 0) Total (Normal)
        fig.add_trace(go.Bar(
            y=df_total['Label names'],
            x=df_total['Total'],
            name=_('Total'),
            orientation='h',
            text=df_total['Total'],
            textposition='auto',
            marker=(dict(color=total_color) if total_color else None)
        ))

        # 1..F) Stacked (by File)
        for idx, col in enumerate(file_cols):
            color = file_colors[idx] if idx < len(file_colors) else None
            fig.add_trace(go.Bar(
                y=df_stack_file['Label names'],
                x=df_stack_file[col],
                name=col,
                orientation='h',
                text=df_stack_file[col],
                textposition='auto',
                marker=(dict(color=color) if color else None)
            ))

        # F+1..end) Stacked (by Coder)
        for idx, col in enumerate(owner_cols):
            color = owner_colors[idx] if idx < len(owner_colors) else None
            fig.add_trace(go.Bar(
                y=df_stack_owner['Label names'],
                x=df_stack_owner[col],
                name=col,
                orientation='h',
                text=df_stack_owner[col],
                textposition='auto',
                marker=(dict(color=color) if color else None)
            ))

        # Visibility masks
        file_len = len(file_cols)
        owner_len = len(owner_cols)
        vis_normal   = [True]  + [False]*file_len + [False]*owner_len
        vis_by_file  = [False] + [True]*file_len  + [False]*owner_len
        vis_by_owner = [False] + [False]*file_len + [True]*owner_len

        for i, v in enumerate(vis_normal):
            fig.data[i].visible = v

        # Layout + buttons
        fig.update_traces(marker_line_width=0.5, marker_line_color='white')
        fig.update_layout(
            title={'text': f"{title}{subtitle}", 'x': 0.5, 'xanchor': 'center'},
            template='seaborn',
            paper_bgcolor='#f6f7fb',
            plot_bgcolor='#f6f7fb',
            barmode='group',
            bargap=0.2,
            height=640,
            margin=dict(l=180, r=40, t=90, b=160),
            xaxis_title=_('Total characters'),
            yaxis_title=_('Label names'),
            legend_title=_('Series'),
            updatemenus=[dict(
                type='buttons',
                showactive=True,
                active=0,
                direction='right',
                x=0.5, xanchor='center',
                y=-0.14, yanchor='top',
                bgcolor='rgba(245,245,245,0.98)',
                bordercolor='#d0d0d0',
                borderwidth=1,
                pad={'l': 10, 'r': 10, 't': 6, 'b': 6},
                buttons=[
                    dict(
                        label=_('Normal (Totals)'),
                        method='update',
                        args=[{'visible': vis_normal}, {'barmode': 'group', 'legend_title_text': _('Series')}]
                    ),
                    dict(
                        label=_('Stacked (by File)'),
                        method='update',
                        args=[{'visible': vis_by_file}, {'barmode': 'stack', 'legend_title_text': _('File')}]
                    ),
                    dict(
                        label=_('Stacked (by Coder)'),
                        method='update',
                        args=[{'visible': vis_by_owner}, {'barmode': 'stack', 'legend_title_text': _('Coder')}]
                    )
                ]
            )],
        )

        # Final polish
        fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.08)', zeroline=False)
        fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.06)')
        fig.add_shape(
            type='rect', xref='paper', yref='paper',
            x0=0, y0=0, x1=1, y1=1,
            line=dict(color='#e5e7eb', width=1),
            fillcolor='rgba(0,0,0,0)',
            layer='below'
        )

        fig.show()
        self.helper_export_html(fig)

    def barchart_code_volume_by_characters(self):

        title = _('Code text by character count')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()

        label_list = []
        totals = []
        per_label_file = []    # list of dicts: {file_name: char_sum}
        per_label_owner = []   # list of dicts: {owner: char_sum}

        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name

        # Cache file names
        file_name_cache = {}

        # --- collect TOTAL (respects owner filter) + per-FILE + per-OWNER (coder) ---
        for c in self.codes:
            # Total chars per label (RESPECTS owner filter)
            sql_total = "select sum(pos1 - pos0) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql_total += " and fid" + file_ids
            cur.execute(sql_total, [c['cid'], owner])
            res_total = cur.fetchone()
            total_chars = (res_total[0] or 0)

            # Per-file breakdown (RESPECTS owner filter)
            sql_pf = "select fid, sum(pos1 - pos0) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql_pf += " and fid" + file_ids
            sql_pf += " group by fid"
            cur.execute(sql_pf, [c['cid'], owner])
            rows_file = cur.fetchall() or []

            filedict = {}
            for fid, s in rows_file:
                if fid is None:
                    continue
                val = (s or 0)
                if fid not in file_name_cache:
                    try:
                        cur2 = self.app.conn.cursor()
                        cur2.execute("select name from source where id=?", [fid])
                        nm = cur2.fetchone()
                        file_name_cache[fid] = nm[0] if nm and nm[0] else f"File {fid}"
                    except Exception:
                        file_name_cache[fid] = f"File {fid}"
                fname = file_name_cache[fid]
                filedict[fname] = filedict.get(fname, 0) + val

            # Per-owner (coder) breakdown (IGNORES owner filter)
            sql_po = "select owner, sum(pos1 - pos0) from code_text where cid=?"
            if file_ids != "":
                sql_po += " and fid" + file_ids
            sql_po += " group by owner"
            cur.execute(sql_po, [c['cid']])
            rows_owner = cur.fetchall() or []

            ownerdict = {}
            for own, s in rows_owner:
                key = own if (own is not None and str(own).strip() != "") else _("(Unassigned)")
                ownerdict[key] = ownerdict.get(key, 0) + (s or 0)

            label_list.append(c['name'])
            totals.append(total_chars)
            per_label_file.append(filedict)
            per_label_owner.append(ownerdict)

        # --- DataFrame of totals; apply cutoff (on Total) ---
        df_total = pd.DataFrame({'Label names': label_list, 'Total': totals})
        mask = df_total['Total'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df_total['Total'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        df_total = df_total[mask]

        if df_total.empty:
            self.ui.textEdit.append(_("No data to display."))
            return

        # sort by total desc
        df_total = df_total.sort_values('Total', ascending=False).reset_index(drop=True)

        # Reorder dicts to match sorted labels
        label_to_files = dict(zip(label_list, per_label_file))
        label_to_owners = dict(zip(label_list, per_label_owner))
        ordered_labels = df_total['Label names'].tolist()

        # --- STACKED (by File): top N files across all labels + "Other" ---
        global_file_sums = defaultdict(int)
        for lab in ordered_labels:
            for fname, val in label_to_files.get(lab, {}).items():
                global_file_sums[fname] += val
        top_files = [fname for fname, _ in sorted(global_file_sums.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N_FILES]]

        stack_file_rows = []
        file_has_other = False
        for lab in ordered_labels:
            row = {'Label names': lab}
            fdict = label_to_files.get(lab, {})
            other_sum = 0
            for fname in top_files:
                row[fname] = fdict.get(fname, 0)
            for fname, val in fdict.items():
                if fname not in top_files:
                    other_sum += val
            if other_sum > 0:
                row['Other (files)'] = other_sum
                file_has_other = True
            stack_file_rows.append(row)
        df_stack_file = pd.DataFrame(stack_file_rows).fillna(0)
        file_cols = top_files + (['Other (files)'] if file_has_other else [])

        # --- STACKED (by Coder): top N owners across all labels + "Other" ---
        global_owner_sums = defaultdict(int)
        for lab in ordered_labels:
            for own, val in label_to_owners.get(lab, {}).items():
                global_owner_sums[own] += val
        top_owners = [own for own, _ in sorted(global_owner_sums.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N_OWNERS]]

        stack_owner_rows = []
        owner_has_other = False
        for lab in ordered_labels:
            row = {'Label names': lab}
            odict = label_to_owners.get(lab, {})
            other_sum = 0
            for own in top_owners:
                row[own] = odict.get(own, 0)
            for own, val in odict.items():
                if own not in top_owners:
                    other_sum += val
            if other_sum > 0:
                row['Other (coders)'] = other_sum
                owner_has_other = True
            stack_owner_rows.append(row)
        df_stack_owner = pd.DataFrame(stack_owner_rows).fillna(0)
        owner_cols = top_owners + (['Other (coders)'] if owner_has_other else [])

        # --- Build figure: Total + per-file stacks + per-owner stacks ---
        fig = go.Figure()

        # 0) Total (Normal)
        fig.add_trace(go.Bar(
            y=df_total['Label names'],
            x=df_total['Total'],
            name=_('Total'),
            orientation='h',
            text=df_total['Total'],
            textposition='auto'
        ))

        # 1..F) Stacked (by File)
        for col in file_cols:
            fig.add_trace(go.Bar(
                y=df_stack_file['Label names'],
                x=df_stack_file[col],
                name=col,
                orientation='h',
                text=df_stack_file[col],
                textposition='auto'
            ))

        # F+1..end) Stacked (by Coder)
        for col in owner_cols:
            fig.add_trace(go.Bar(
                y=df_stack_owner['Label names'],
                x=df_stack_owner[col],
                name=col,
                orientation='h',
                text=df_stack_owner[col],
                textposition='auto'
            ))

        # Visibility masks
        total_len = 1
        file_len = len(file_cols)
        owner_len = len(owner_cols)
        vis_normal = [True] + [False]*file_len + [False]*owner_len
        vis_by_file = [False] + [True]*file_len + [False]*owner_len
        vis_by_owner = [False] + [False]*file_len + [True]*owner_len

        for i, v in enumerate(vis_normal):
            fig.data[i].visible = v

        # Layout + buttons (bottom)
        fig.update_traces(marker_line_width=0.5, marker_line_color='white')
        fig.update_layout(
            title={'text': f"{title}{subtitle}", 'x': 0.5, 'xanchor': 'center'},
            template='seaborn',
            paper_bgcolor='#f6f7fb',
            plot_bgcolor='#f6f7fb',
            barmode='group',
            bargap=0.2,
            height=640,
            margin=dict(l=180, r=40, t=90, b=160),
            xaxis_title=_('Total characters'),
            yaxis_title=_('Label names'),
            legend_title=_('Series'),
            updatemenus=[dict(
                type='buttons',
                showactive=True,
                active=0,
                direction='right',
                x=0.5, xanchor='center',
                y=-0.14, yanchor='top',
                bgcolor='rgba(245,245,245,0.98)',
                bordercolor='#d0d0d0',
                borderwidth=1,
                pad={'l': 10, 'r': 10, 't': 6, 'b': 6},
                buttons=[
                    dict(
                        label=_('Normal (Totals)'),
                        method='update',
                        args=[
                            {'visible': vis_normal},
                            {'barmode': 'group', 'legend_title_text': _('Series')}
                        ]
                    ),
                    dict(
                        label=_('Stacked (by File)'),
                        method='update',
                        args=[
                            {'visible': vis_by_file},
                            {'barmode': 'stack', 'legend_title_text': _('File')}
                        ]
                    ),
                    dict(
                        label=_('Stacked (by Coder)'),
                        method='update',
                        args=[
                            {'visible': vis_by_owner},
                            {'barmode': 'stack', 'legend_title_text': _('Coder')}
                        ]
                    )
                ]
            )],
        )

        # Soft grid + subtle border
        fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.08)', zeroline=False)
        fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.06)')
        fig.add_shape(
            type='rect', xref='paper', yref='paper',
            x0=0, y0=0, x1=1, y1=1,
            line=dict(color='#e5e7eb', width=1),
            fillcolor='rgba(0,0,0,0)',
            layer='below'
        )

        fig.show()
        self.helper_export_html(fig)


    def barchart_code_volume_by_area(self):
        """ Codes by image area volume. """

        title = _('Code volume by image area (pixels)')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        for c in self.codes:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Pixels': values}
        df = pd.DataFrame(data)
        mask = df['Pixels'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Pixels'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.bar(df[mask], x='Pixels', y='Code names', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def barchart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        title = _('Code volume by audio/video segments (milliseconds)')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        for c in self.codes:
            sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total millisecs': values}
        df = pd.DataFrame(data)
        mask = df['Total millisecs'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Total millisecs'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.bar(df[mask], x='Total millisecs', y='Code names', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def show_pie_chart(self):
        """ Various pie chart options.
        Index numbering matches order of options, set up in init
        """

        chart_type_index = self.ui.comboBox_pie_charts.currentIndex()
        if chart_type_index < 1:
            return
        color_palette = self.selected_color_palette
        print("Color palette in update_selected_chart:", color_palette)
        self.get_selected_categories_and_codes()
        if chart_type_index == 1:  # Code frequency
            self.hierarchy_code_frequency(color_palette)
        if chart_type_index == 2:  # Code by characters
            self.piechart_code_volume_by_characters(color_palette)
        #if chart_type_index == 3:  # Code by image area
            #self.piechart_code_volume_by_area()
        #if chart_type_index == 4:  # Code by audio/video segments
           # self.piechart_code_volume_by_segments()
        self.ui.comboBox_pie_charts.setCurrentIndex(0)

    def hierarchy_code_frequency(self, color_palette=None):
        """ Code for rendering the hierarchy chart, using the selected color palette. """
        title = "Chart of Label and Category Counts"
        owner, subtitle = self.owner_and_subtitle_helper()
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name:
            subtitle += case_file_name

        # --- gather coded cids from DB (text, image, av) ---
        coded = []
        cur = self.app.conn.cursor()
        for table, id_field in [("code_text", "fid"), ("code_image", "id"), ("code_av", "id")]:
            sql = f"SELECT cid FROM {table} WHERE owner LIKE ?"
            if file_ids:
                sql += f" AND {id_field}" + file_ids
            cur.execute(sql, [owner])
            coded.extend(cur.fetchall())

        # --- code counts ---
        cid_counts = {}
        for (cid,) in coded:
            cid_counts[cid] = cid_counts.get(cid, 0) + 1
        for code in self.codes:
            code["count"] = cid_counts.get(code["cid"], 0)

        # --- category lookups ---
        parentid_by_id = {c["catid"]: c.get("supercatid") for c in self.categories}
        name_by_id     = {c["catid"]: c["name"] for c in self.categories}
        top_names      = [c["name"] for c in self.categories if not c.get("supercatid")]  # center nodes

        def topcat_name(catid):
            cur_cat = catid
            seen = set()
            while parentid_by_id.get(cur_cat):
                if cur_cat in seen:  # safety
                    break
                seen.add(cur_cat)
                cur_cat = parentid_by_id[cur_cat]
            return name_by_id.get(cur_cat, "")

        # --- build children (codes → top category) and center values (sum of their codes) ---
        top_sums = {}
        children = []
        for code in self.codes:
            cnt = int(code.get("count", 0))
            if cnt == 0:
                continue
            top = topcat_name(code.get("catid"))
            top_sums[top] = top_sums.get(top, 0) + cnt
            children.append({"item": code["name"], "value": cnt, "parent": top})

        centers = [{"item": nm, "value": int(top_sums.get(nm, 0)), "parent": ""} for nm in top_names]
        df = pd.DataFrame(centers + children)

        # --- optional cutoff (keep centers; filter children) ---
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff:
            try:
                thr = int(cutoff)
                centers_df = df[df["parent"] == ""]
                kids_df    = df[df["parent"] != ""]
                kids_df    = kids_df[kids_df["value"] >= thr]
                df = pd.concat([centers_df, kids_df], ignore_index=True)
                subtitle += f" (Values ≥ {cutoff})"
            except ValueError:
                pass

        # --- POST-FILTER FIX: ensure every center has children & parent equals sum(children) ---
        centers_df = df[df["parent"] == ""].copy()
        kids_df    = df[df["parent"] != ""].copy()

        # recompute child sums by parent using remaining kids
        child_sums = kids_df.groupby("parent")["value"].sum().to_dict()

        fixed_centers = []
        extra_kids = []

        for _, c in centers_df.iterrows():
            name = c["item"]
            sum_children = int(child_sums.get(name, 0))

            if sum_children > 0:
                # align parent value to children sum
                fixed_centers.append({
                    "id": f"cat::{name}",
                    "parent_id": "",
                    "item": name,
                    "value": sum_children
                })
            else:
                # no children -> create a duplicate child, give it a minimal positive value
                dup_val = max(int(c["value"]), 1)
                fixed_centers.append({
                    "id": f"cat::{name}",
                    "parent_id": "",
                    "item": name,
                    "value": dup_val
                })
                extra_kids.append({
                    "id": f"dup::{name}",
                    "parent_id": f"cat::{name}",
                    "item": name,
                    "value": dup_val
                })

        fixed_kids = []
        for _, r in kids_df.iterrows():
            fixed_kids.append({
                "id": f"code::{r['item']}::{r['parent']}",
                "parent_id": f"cat::{r['parent']}",
                "item": r["item"],
                "value": int(r["value"])
            })

        d2 = pd.DataFrame(fixed_centers + fixed_kids + extra_kids)

        # --- COLORING: center solid, children gradient per parent based on value ---
        parents_df = d2[d2["parent_id"] == ""].copy()
        parent_ids = list(parents_df["id"])

        # base palette: use user palette if list, else Plotly qualitative
        if isinstance(color_palette, list) and color_palette:
            base_palette = color_palette
        else:
            base_palette = qualitative.Plotly

        base_colors = {}
        for i, pid in enumerate(parent_ids):
            base_colors[pid] = base_palette[i % len(base_palette)]

        def hex_to_hls(hex_color):
            """Return (h, l, s) for a hex color."""
            hex_color = hex_color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = "".join([c * 2 for c in hex_color])
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            return colorsys.rgb_to_hls(r, g, b)

        def hls_to_hex(h, l, s):
            r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
            return "#{:02x}{:02x}{:02x}".format(int(r2 * 255), int(g2 * 255), int(b2 * 255))

        # per-parent min/max among children (for gradient)
        kids_only = d2[d2["parent_id"] != ""]
        if not kids_only.empty:
            stats = kids_only.groupby("parent_id")["value"].agg(["min", "max"]).to_dict("index")
        else:
            stats = {}

        # parent totals & child counts (for equality rule)
        parent_totals = parents_df.set_index("id")["value"].to_dict()
        child_counts_by_parent = d2[d2["parent_id"] != ""].groupby("parent_id")["id"].count().to_dict()

        colors = []
        for _, row in d2.iterrows():
            if row["parent_id"] == "":
                # center: solid base color
                pid = row["id"]
                base = base_colors.get(pid, "#888888")
                colors.append(base)
            else:
                pid = row["parent_id"]
                base = base_colors.get(pid, "#888888")

                child_val    = row["value"]
                parent_total = parent_totals.get(pid, 0) or 1
                n_children   = child_counts_by_parent.get(pid, 0)

                # STRICT RULE:
                # if there is only ONE child and its count == parent's count
                # -> use EXACT parent color (no gradient)
                if n_children == 1 and child_val == parent_total:
                    colors.append(base)
                    continue

                # gradient based on min/max among children
                st = stats.get(pid, None)
                if st and st["max"] != st["min"]:
                    rel = (child_val - st["min"]) / (st["max"] - st["min"])
                else:
                    rel = 0.5  # all equal, middle shade

                # get base HLS (parent color)
                h, base_l, s = hex_to_hls(base)

                # --- corrected gradient logic ---
                # parent (base_l) is darkest; children must be strictly lighter
                # L_light: lighter bound (toward white)
                L_light = min(1.0, base_l + (1.0 - base_l) * 0.3)

                # how much room we have to lighten
                span = max(1e-6, L_light - base_l)

                # L_dark: slightly lighter than parent (so no child = exactly parent color)
                # darkest child is 20% along the way from parent to L_light
                L_dark = base_l + span * 0.2

                # clamp rel to [0, 1] to be safe
                rel = max(0.0, min(1.0, rel))

                # rel = 1.0 -> L_dark (closest to parent, but still lighter)
                # rel = 0.0 -> L_light (lightest)
                l_child = L_light - (L_light - L_dark) * rel

                colors.append(hls_to_hex(h, l_child, s))

        d2["color"] = colors

        # --- plot (exactly two levels; full outer ring) with go.Sunburst ---
        fig = go.Figure(
            go.Sunburst(
                ids=d2["id"],
                labels=d2["item"],
                parents=d2["parent_id"],
                values=d2["value"],
                branchvalues="total",   # parent size == sum(children)
                maxdepth=2,
                marker=dict(
                    colors=d2["color"]
                ),
                leaf=dict(opacity=1),   # prevent dimming of leaves
                hovertemplate="<b>%{label}</b><br>"
                            "Parent: %{parent}<br>"
                            "Count: %{value}<br>"
                            "% of parent: %{percentParent:.1%}<br>"
                            "% of total: %{percentRoot:.1%}<extra></extra>"
            )
        )

        fig.update_layout(
            title=title + " " + subtitle,
            uniformtext_minsize=10,
            uniformtext_mode="hide",
            margin=dict(l=0, r=0, t=60, b=0),
            showlegend=False
        )

        fig.show()
        self.helper_export_html(fig)

    def piechart_code_volume_by_characters(self, color_palette=None):
        """ Code for rendering the pie chart of label text by character count, using the selected color palette. """
        title = 'Label text by character count'
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()

        # --- same inputs/queries as before: per-code total characters ---
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name

        for c in self.codes:
            sql = "select sum(pos1 - pos0) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(pos1 - pos0) from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append((res[0] or 0))  # keep None as 0

        # Build initial dataframe from exactly the same inputs
        df_raw = pd.DataFrame({'Label names': labels, 'Total characters': values})

        # --- category lookups (for two-level structure) ---
        parentid_by_id = {c["catid"]: c.get("supercatid") for c in self.categories}
        name_by_id     = {c["catid"]: c["name"] for c in self.categories}
        top_names      = [c["name"] for c in self.categories if not c.get("supercatid")]

        # helper: resolve top category name for a given category id
        def topcat_name(catid):
            curid = catid
            seen = set()
            while parentid_by_id.get(curid):
                if curid in seen:
                    break
                seen.add(curid)
                curid = parentid_by_id[curid]
            return name_by_id.get(curid, "")

        # map code -> cat/topcat using self.codes (no DB changes)
        code_to_cat = {c["name"]: c.get("catid") for c in self.codes}
        code_to_top = {nm: topcat_name(code_to_cat.get(nm)) for nm in labels}

        # children rows (codes) using the original totals (characters)
        kids = []
        top_sums = {}
        for _, r in df_raw.iterrows():
            code = r['Label names']
            val  = int(r['Total characters'] or 0)
            if val <= 0:
                continue  # drop zero-size kids (centers are handled below)
            top = code_to_top.get(code, "")
            kids.append({"item": code, "value": val, "parent": top})
            top_sums[top] = top_sums.get(top, 0) + val

        # center rows (top categories) with preliminary totals
        centers = [{"item": nm, "value": int(top_sums.get(nm, 0)), "parent": ""} for nm in top_names]

        df = pd.DataFrame(centers + kids)

        # --- optional cutoff (filter children only; keep all centers) ---
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff:
            try:
                thr = int(cutoff)
                centers_df = df[df["parent"] == ""]
                kids_df    = df[(df["parent"] != "") & (df["value"] >= thr)]
                df = pd.concat([centers_df, kids_df], ignore_index=True)
                subtitle += _(" (Values ≥ ") + cutoff + ")"
            except ValueError:
                pass

        # --- Post-filter fix: align parent sizes to remaining children; duplicate lone parents as their own child ---
        centers_df = df[df["parent"] == ""].copy()
        kids_df    = df[df["parent"] != ""].copy()
        child_sums = kids_df.groupby("parent")["value"].sum().to_dict()

        fixed_centers = []
        extra_kids = []
        for _, c in centers_df.iterrows():
            name = c["item"]
            sum_children = int(child_sums.get(name, 0))
            if sum_children > 0:
                fixed_centers.append({
                    "id": f"cat::{name}",
                    "parent_id": "",
                    "item": name,
                    "value": sum_children
                })
            else:
                dup_val = max(int(c["value"]), 1)  # keep visible center and a tiny child if it had no kids
                fixed_centers.append({
                    "id": f"cat::{name}",
                    "parent_id": "",
                    "item": name,
                    "value": dup_val
                })
                extra_kids.append({
                    "id": f"dup::{name}",
                    "parent_id": f"cat::{name}",
                    "item": name,
                    "value": dup_val
                })

        fixed_kids = []
        for _, r in kids_df.iterrows():
            fixed_kids.append({
                "id": f"code::{r['item']}::{r['parent']}",
                "parent_id": f"cat::{r['parent']}",
                "item": r["item"],
                "value": int(r["value"])  # characters
            })

        d2 = pd.DataFrame(fixed_centers + fixed_kids + extra_kids)

        # ---------- COLORING: parent solid, children gradient by characters (same logic as hierarchy_code_frequency) ----------

        parents_df = d2[d2["parent_id"] == ""].copy()
        parent_ids = list(parents_df["id"])

        # base palette: use user palette if list, else Plotly qualitative
        if isinstance(color_palette, list) and color_palette:
            base_palette = color_palette
        else:
            base_palette = qualitative.Plotly

        base_colors = {}
        for i, pid in enumerate(parent_ids):
            base_colors[pid] = base_palette[i % len(base_palette)]

        def hex_to_hls(hex_color):
            hex_color = hex_color.lstrip("#")
            if len(hex_color) == 3:
                hex_color = "".join([c * 2 for c in hex_color])
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            return colorsys.rgb_to_hls(r, g, b)

        def hls_to_hex(h, l, s):
            r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
            return "#{:02x}{:02x}{:02x}".format(int(r2 * 255), int(g2 * 255), int(b2 * 255))

        # per-parent min/max among children (for gradient)
        kids_only = d2[d2["parent_id"] != ""]
        if not kids_only.empty:
            stats = kids_only.groupby("parent_id")["value"].agg(["min", "max"]).to_dict("index")
        else:
            stats = {}

        # parent totals & child counts (for the equality rule)
        parent_totals = parents_df.set_index("id")["value"].to_dict()
        child_counts_by_parent = d2[d2["parent_id"] != ""].groupby("parent_id")["id"].count().to_dict()

        colors = []
        for _, row in d2.iterrows():
            if row["parent_id"] == "":
                # center: solid base color
                pid = row["id"]
                base = base_colors.get(pid, "#888888")
                colors.append(base)
            else:
                pid = row["parent_id"]
                base = base_colors.get(pid, "#888888")

                child_val    = row["value"]
                parent_total = parent_totals.get(pid, 0) or 1
                n_children   = child_counts_by_parent.get(pid, 0)

                # STRICT RULE:
                # if there is only ONE child and its value == parent's value
                # -> use EXACT parent color (no gradient)
                if n_children == 1 and child_val == parent_total:
                    colors.append(base)
                    continue

                # gradient based on min/max among children
                st = stats.get(pid, None)
                if st and st["max"] != st["min"]:
                    rel = (child_val - st["min"]) / (st["max"] - st["min"])
                else:
                    rel = 0.5  # all equal, middle shade

                # get base HLS (parent color)
                h, base_l, s = hex_to_hls(base)

                # --- corrected gradient logic (same as hierarchy_code_frequency) ---
                # parent (base_l) is darkest; children must be strictly lighter
                # L_light: lighter bound (toward white)
                L_light = min(1.0, base_l + (1.0 - base_l) * 0.3)

                # how much room we have to lighten
                span = max(1e-6, L_light - base_l)

                # L_dark: slightly lighter than parent (so no child = exactly parent color)
                # darkest child is 20% along the way from parent to L_light
                L_dark = base_l + span * 0.2

                # clamp rel to [0, 1]
                rel = max(0.0, min(1.0, rel))

                # rel = 1.0 -> L_dark (closest to parent, but still lighter)
                # rel = 0.0 -> L_light (lightest)
                l_child = L_light - (L_light - L_dark) * rel

                colors.append(hls_to_hex(h, l_child, s))

        d2["color"] = colors

        # --- plot two-level sunburst with go.Sunburst ---
        fig = go.Figure(
            go.Sunburst(
                ids=d2["id"],
                labels=d2["item"],
                parents=d2["parent_id"],
                values=d2["value"],       # character-based size
                branchvalues="total",
                maxdepth=2,
                marker=dict(
                    colors=d2["color"]
                ),
                leaf=dict(opacity=1),     # important: no dimming of leaves
                hovertemplate="<b>%{label}</b><br>"
                            "Parent: %{parent}<br>"
                            "Characters: %{value}<br>"
                            "% of parent: %{percentParent:.1%}<br>"
                            "% of total: %{percentRoot:.1%}<extra></extra>"
            )
        )

        fig.update_layout(
            title=title + " " + subtitle,
            uniformtext_minsize=10,
            uniformtext_mode="hide",
            margin=dict(l=0, r=0, t=60, b=0),
            showlegend=False
        )

        fig.show()
        self.helper_export_html(fig)

    def piechart_code_volume_by_area(self):
        """ Codes by image area volume. """

        title = _('Code volume by image area (pixels)')
        owner, subtitle = self.owner_and_subtitle_helper()
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.codes:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total pixels': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total pixels'] != 0
        if cutoff != "":
            mask = df['Total pixels'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.pie(df[mask], values='Total pixels', names='Code names', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def piechart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        title = _('Code volume by audio/video segments (milliseconds)')
        owner, subtitle = self.owner_and_subtitle_helper()
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        values = []
        labels = []
        cur = self.app.conn.cursor()
        for c in self.codes:
            sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total millisecs': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total millisecs'] != 0
        if cutoff != "":
            mask = df['Total millisecs'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.pie(df[mask], values='Total millisecs', names='Code names', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    '''def show_hierarchy_chart(self):
        """ Disp;lay treemaps and sunburst charts.
        https://plotly.com/python/sunburst-charts/
        Index numbering matches order of options, set up in init
        """

        chart_type_index = self.ui.comboBox_sunburst_charts.currentIndex()
        if chart_type_index < 1:
            return
        self.get_selected_categories_and_codes()
        self.helper_for_matching_category_and_code_name()
        if chart_type_index == 1:  # Code frequency sunburst
            self.hierarchy_code_frequency("sunburst")
        #if chart_type_index == 2:  # Code frequency treemap
            #self.hierarchy_code_frequency("treemap")
        if chart_type_index == 2:  # Code by characters sunburst
            self.hierarchy_code_volume_by_characters("sunburst")
        #if chart_type_index == 4:  # Code by characters treemap
            #self.hierarchy_code_volume_by_characters("treemap")
        if chart_type_index == 3:  # Code by image area sunburst
            self.hierarchy_code_volume_by_area("sunburst")
        #if chart_type_index == 6:  # Code by image area treemap
            #self.hierarchy_code_volume_by_area("treemap")
        if chart_type_index == 4:  # Code by A/V sunburst
            self.hierarchy_code_volume_by_segments("sunburst")
        #if chart_type_index == 8:  # Code by A/V treemap
            #self.hierarchy_code_volume_by_segments("treemap")
        self.ui.comboBox_sunburst_charts.setCurrentIndex(0)

    def helper_for_matching_category_and_code_name(self):
        """ This is for qdpx imported projects.
        Might be a quirk of importation, but category names and code names can match.
         e.g. Maxqda, Nvivo allows a category name and a code name to be the same. (the same node).
         This causes hierarchy charts to not display.
         Solution, add spaces after the code_name to separate it out. """

        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

    def hierarchy_code_frequency(self, chart="sunburst"):
        """ Count of codes across text, images and A/V.
        Calculates code count and category count and displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of counts of codes and categories')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        coded_data = []
        cur = self.app.conn.cursor()
        sql_t = "select cid from code_text where owner like ?"
        if file_ids != "":
            sql_t = "select cid from code_text where owner like ? and fid" + file_ids
        cur.execute(sql_t, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        sql_i = "select cid from code_image where owner like ?"
        if file_ids != "":
            sql_i = "select cid from code_image where owner like ? and id" + file_ids
        cur.execute(sql_i, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        sql_av = "select cid from code_av where owner like ?"
        if file_ids != "":
            sql_av = "select cid from code_av where owner like ? and id" + file_ids
        cur.execute(sql_av, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += 1
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)

    def hierarchy_code_volume_by_characters(self, chart="sunburst"):
        """ Count of code characters across text files.
            Calculates code count and category count and displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of counts of coded text - total characters')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        coded_data = []
        cur = self.app.conn.cursor()
        sql = "select cid, pos1-pos0 from code_text where owner like ?"
        if file_ids != "":
            sql = "select cid, pos1-pos0 from code_text where owner like ?and fid" + file_ids
        cur.execute(sql, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[1]
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)

    def hierarchy_code_volume_by_area(self, chart="sunburst"):
        """ Count of coded image areas across image files.
            Displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of coded image areas - pixels')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        coded_data = []
        cur = self.app.conn.cursor()
        sql = "select cid, cast(width as int) * cast(height as int) from code_image where owner like ?"
        if file_ids != "":
            sql = "select cid, cast(width as int) * cast(height as int) from code_image where owner like ? and id" + file_ids
        cur.execute(sql, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[1]
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)

    def hierarchy_code_volume_by_segments(self, chart="sunburst"):
        """ Count of codes segment durations across audio/video files.
            Displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of coded audio/video segments - milliseconds')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        coded_data = []
        cur = self.app.conn.cursor()
        sql = "select cid, pos1-pos0 from code_av where owner like ?"
        if file_ids != "":
            sql = "select cid, pos1-pos0 from code_av where owner like ? and id" + file_ids
        cur.execute(sql, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[1]
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)'''

    # ATTRIBUTES CHARTS SECTION
    def fill_combobox_attributes(self):
        """ Fill attributes if case or file is selected.
            attribute keys = name, memo, caseOrFile, valuetype
        """

        list_char = [""]
        list_num = [""]
        if self.ui.radioButton_file.isChecked():
            for a in self.attributes:
                if a['caseOrFile'] == "file" and a['valuetype'] == "character":
                    list_char.append(a['name'])
                if a['caseOrFile'] == "file" and a['valuetype'] == "numeric":
                    list_num.append(a['name'])
        else:
            for a in self.attributes:
                if a['caseOrFile'] == "case" and a['valuetype'] == "character":
                    list_char.append(a['name'])
                if a['caseOrFile'] == "case" and a['valuetype'] == "numeric":
                    list_num.append(a['name'])
        self.ui.comboBox_num_attributes.blockSignals(True)
        self.ui.comboBox_char_attributes.blockSignals(True)
        self.ui.comboBox_num_attributes.clear()
        self.ui.comboBox_char_attributes.clear()
        self.ui.comboBox_char_attributes.addItems(list_char)
        self.ui.comboBox_num_attributes.addItems(list_num)
        self.ui.comboBox_num_attributes.blockSignals(False)
        self.ui.comboBox_char_attributes.blockSignals(False)

    def character_attribute_charts(self):
        """ Character attributes are displayed as counts via bar charts. """

        file_or_case = "case"
        if self.ui.radioButton_file.isChecked():
            file_or_case = "file"
        attribute = self.ui.comboBox_char_attributes.currentText()
        title = _("Attribute bar chart")
        subtitle = "<br><sup>" + _(file_or_case) + _(" attribute: ") + attribute
        self.ui.comboBox_char_attributes.blockSignals(True)
        self.ui.comboBox_char_attributes.setCurrentIndex(0)
        self.ui.comboBox_char_attributes.blockSignals(False)

        cur = self.app.conn.cursor()
        cur.execute(
            "select value, count(value) from attribute where attr_type=? and name=? group by value order by upper(value)",
            [file_or_case, attribute])
        res = cur.fetchall()
        labels = []
        values = []
        for r in res:
            labels.append(r[0])
            values.append(r[1])
        # Create pandas DataFrame
        data = {'Value': labels, 'Count': values}
        df = pd.DataFrame(data)
        fig = px.bar(df, x='Count', y='Value', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def numeric_attribute_charts(self):
        """ Character attributes are displayed as boxplot charts. """

        file_or_case = "case"
        if self.ui.radioButton_file.isChecked():
            file_or_case = "file"
        attribute = self.ui.comboBox_num_attributes.currentText()
        title = _("Attribute histogram")
        subtitle = "<br><sup>" + _(file_or_case) + _(" attribute: ") + attribute
        self.ui.comboBox_num_attributes.blockSignals(True)
        self.ui.comboBox_num_attributes.setCurrentIndex(0)
        self.ui.comboBox_num_attributes.blockSignals(False)

        cur = self.app.conn.cursor()
        cur.execute("select cast(value as int) from attribute where attr_type=? and name=?",
                    [file_or_case, attribute])
        res = cur.fetchall()
        values = []
        for r in res:
            values.append(r[0])
        # Create pandas DataFrame
        data = {attribute: values}
        df = pd.DataFrame(data)
        fig = px.histogram(df, x=attribute, title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    # HEATMAP CHARTS SECTION
    def heatmap_counter_by_file_and_code(self, owner, fid, cid):
        """ Get count of codings for this code and this file.
         Use spinbox_count_max to limit maximum counts for codes.
         This is to allow a wider spread of head map colours when there are extreme count differences.
         """

        max_count = int(self.ui.lineEdit_count_limiter.text())
        count = 0
        cur = self.app.conn.cursor()
        sql_t = "select count(cid) from code_text where owner like ? and cid=? and fid=?"
        cur.execute(sql_t, [owner, cid, fid])
        result_t = cur.fetchone()
        if result_t is not None:
            count += result_t[0]
        sql_i = "select count(cid) from code_image where owner like ? and cid=? and id=?"
        cur.execute(sql_i, [owner, cid, fid])
        result_i = cur.fetchone()
        if result_i is not None:
            count += result_i[0]
        sql_av = "select count(cid) from code_av where owner like ? and cid=? and id=?"
        cur.execute(sql_av, [owner, cid, fid])
        result_av = cur.fetchone()
        if result_av is not None:
            count += result_av[0]
        if 0 < max_count < count:
            count = max_count
        return count

    def make_heatmap(self):
        """ Make a heat map based on cases or files.
        Use code count as the basic unit of measurement.
        Filters: Coder, selected category.
        Exclude from filters: Count; selected file; selected case
        TODO include in filters: Selected Attributes for Cases - uses attribute_file_ids and attributes_msg
        """

        self.get_selected_categories_and_codes()
        codes = deepcopy(self.codes)
        if len(codes) > 40:
            codes = codes[:40]
            Message(self.app, _("Too many codes"), _("Too many codes for display. Restricted to 40")).exec()
        # Filters
        heatmap_type = self.ui.comboBox_heatmap.currentText()
        if heatmap_type == "":
            return
        title = heatmap_type + " " + _("Matrix View")
        self.get_selected_categories_and_codes()
        y_labels = []
        for c in codes:
            y_labels.append(c['name'])
        category = self.ui.comboBox_category.currentText()
        self.ui.lineEdit_filter.setText("")
        self.ui.comboBox_case.setCurrentIndex(0)
        self.ui.comboBox_file.setCurrentIndex(0)
        owner, subtitle = self.owner_and_subtitle_helper()

        # Get all the coded data
        data = []
        x_labels = []
        cur = self.app.conn.cursor()
        if heatmap_type == "File":
            if not self.attribute_file_ids:
                sql = "select id, name from source order by name"
                cur.execute(sql)
                files = cur.fetchall()
            else:
                attr_msg, file_ids_txt = self.get_file_ids()
                subtitle += attr_msg
                sql = "select id, name from source where id " + file_ids_txt + " order by name"
                cur.execute(sql)
                files = cur.fetchall()
            if len(files) > 40:
                files = files[:40]
                Message(self.app, _("Too many files"), _("Too many files for display. Restricted to 40")).exec()
            for file_ in files:
                x_labels.append(file_[1])
            # Calculate the frequency of each code in each file
            # Each row is a code, each column is a file
            for code_ in codes:
                code_counts = []
                for file_ in files:
                    code_counts.append(self.heatmap_counter_by_file_and_code(owner, file_[0], code_['cid']))
                data.append(code_counts)
        if heatmap_type == "Case":
            if not self.attribute_case_ids_and_names:  # self.attribute_file_ids:
                sql = "select caseid, name from cases order by name"
                cur.execute(sql)
                cases = cur.fetchall()
                if len(cases) > 40:
                    cases = cases[:40]
                    Message(self.app, _("Too many cases"), _("Too many cases for display. Restricted to 40")).exec()
                for c in cases:
                    x_labels.append(c[1])
                # Calculate the frequency of each code in each file
                # Each row is a code, each column is a file
                for code_ in codes:
                    code_counts = []
                    for c in cases:
                        cur.execute("SELECT fid FROM case_text where caseid=?", [c[0]])
                        fids = cur.fetchall()
                        case_counts = 0
                        for fid in fids:
                            case_counts += self.heatmap_counter_by_file_and_code(owner, fid[0], code_['cid'])
                        code_counts.append(case_counts)
                    data.append(code_counts)
            else:
                attr_msg, file_ids_txt = self.get_file_ids()
                print(self.attribute_case_ids_and_names)
                for c in self.attribute_case_ids_and_names:
                    x_labels.append(c[1])
                subtitle += attr_msg
                # Calculate the frequency of each code in each file
                # Each row is a code, each column is a file
                for code_ in codes:
                    code_counts = []
                    for c in self.attribute_case_ids_and_names:
                        cur.execute("SELECT fid FROM case_text where caseid=?", [c[0]])
                        fids = cur.fetchall()
                        # TODO revise fids if file parameters selected
                        case_counts = 0
                        for fid in fids:
                            case_counts += self.heatmap_counter_by_file_and_code(owner, fid[0], code_['cid'])
                        code_counts.append(case_counts)
                    data.append(code_counts)
        # Create the plot
        fig = px.imshow(data,
                        labels=dict(x=heatmap_type, y="Codes", color="Count"),
                        x=x_labels,
                        y=y_labels,
                        title=title + subtitle,
                        text_auto=True #this adds numbers on the boxes
                        )
        fig.update_xaxes(side="top")
        fig.show()
        self.helper_export_html(fig)
        self.ui.comboBox_heatmap.blockSignals(True)
        self.ui.comboBox_heatmap.setCurrentIndex(0)
        self.ui.comboBox_heatmap.blockSignals(False)
