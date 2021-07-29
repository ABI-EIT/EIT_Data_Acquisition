#!/usr/bin/env python


#############################################################################
##
## Copyright (C) 2017 Riverbank Computing Limited.
## Copyright (C) 2010 Nokia Corporation and/or its subsidiary(-ies).
## All rights reserved.
##
## This file is part of the examples of PyQt.
##
## $QT_BEGIN_LICENSE:BSD$
## You may use this file under the terms of the BSD license as follows:
##
## "Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions are
## met:
##   * Redistributions of source code must retain the above copyright
##     notice, this list of conditions and the following disclaimer.
##   * Redistributions in binary form must reproduce the above copyright
##     notice, this list of conditions and the following disclaimer in
##     the documentation and/or other materials provided with the
##     distribution.
##   * Neither the name of Nokia Corporation and its Subsidiary(-ies) nor
##     the names of its contributors may be used to endorse or promote
##     products derived from this software without specific prior written
##     permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
## A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
## OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
## SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
## LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
## DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
## THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
## (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
## OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
## $QT_END_LICENSE$
##
#############################################################################


from PyQt5.QtCore import (QAbstractItemModel, QFile, QIODevice,
        QItemSelectionModel, QModelIndex, Qt)
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QItemEditorFactory
from PyQt5 import uic, QtWidgets
from tree_model import TreeModel
from math import ceil
import json
Ui_MainWindow, QMainWindow = uic.loadUiType("mainwindow.ui")


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)

        self.setupUi(self)

        with open("data.json", "r") as f:
            data = json.load(f)

        model = TreeModel(data)

        view = DictView(model=model)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(view)
        self.centralwidget.setLayout(layout)


class DictView(QWidget):
    def __init__(self, model=None, parent=None, cols=None):
        super(DictView, self).__init__(parent)
        self.model = model

        # Build layout from settings
        layout_kwargs = {} if cols is None else {"cols": cols}
        form_layout = self.build_layout(**layout_kwargs)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(form_layout)
        self.setLayout(layout)

    def set_model(self, model: TreeModel):
        self.model = model
        self.model.dataChanged.connect(self.update_view)

    def update_view(self):
        pass

    def get_model_items_flat(self, item_index):
        for i in range(self.model.getItem(item_index).childCount()):
            child_index = self.model.index(i, 0, parent=item_index)
            key = self.model.data(child_index)
            value = self.model.data(child_index)
            return [(key, value), *self.get_model_items_flat(child_index)]

        return []

    def get_editor(self, value):
        return QItemEditorFactory.defaultFactory().createEditor(type(value), QWidget())

    def build_layout(self, cols=2):

        items = self.get_model_items_flat(QModelIndex())

        h_layout = QtWidgets.QHBoxLayout()
        forms = [QtWidgets.QFormLayout() for _ in range(cols)]
        for form in forms:
            h_layout.addLayout(form)

        num_items = len(items)
        for i, (key, value) in enumerate(items):
            # Find which column to put the setting in. Columns are filled equally, with remainder to the left. Each column
            # is filled before proceeding to the next.
            f_index = 0
            for j in range(cols):
                if (i + 1) <= ceil((j + 1) * num_items / cols):
                    f_index = j
                    break

            # input_widget = self.get_editor(value)
            input_widget = QtWidgets.QLineEdit(str(value))

            label = QtWidgets.QLabel(key)
            forms[f_index].addRow(label, input_widget)

        return h_layout


if __name__ == '__main__':

    import sys

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())