from PyQt5.QtCore import (QAbstractItemModel, QFile, QIODevice,
        QItemSelectionModel, QModelIndex, Qt)


class DictTreeItem(object):
    """
    DictTreeItem is used to build a heirarchical tree structure of items to make up the data in TreeModel.
    It represents a dict while implementing part of the QAbstractItemModel interface.
    Each DictTreeItem stores a key representing a key in the underlying dict, plus a reference to the parent item.
    For the purposes of the model/view architecture, the key is stored in column 0. The corresponding value is
    accessed via a request for the data in column 1. The value is retrieved from the underlying dict using the
    key plus a recursive search of the parent keys.
    """
    def __init__(self, data: dict, key: str=None, parent=None):
        self.dict_data = data
        self.parentItem = parent
        self.itemKey = key
        self.childItems = []

    def child(self, row):
        if row < 0 or row >= len(self.childItems):
            return None
        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def childNumber(self):
        if self.parentItem != None:
            return self.parentItem.childItems.index(self)
        return 0

    def columnCount(self):
        return 2

    def data(self, column):
        if column < 0 or column > self.columnCount()-1 or self.parent() is None:
            return None
        elif column == 0:
            return self.itemKey
        elif column == 1:
            return self.get_dict_item(self.itemKey, self.parent())

    def insertChild(self, position, data_dict, key):
        if position < 0 or position > len(self.childItems):
            return False

        item = DictTreeItem(data_dict, key, self)
        self.childItems.insert(position, item)

        return True

    def parent(self):
        return self.parentItem

    def setData(self, column, value):
        if column < 0 or column >= len(self.itemData):
            return False

        self.itemData[column] = value

        return True

    @staticmethod
    def get_dict_item(key, item: "DictTreeItem"):
        if item.parent() is None:
            return item.dict_data[key]
        else:
            return item.get_dict_item(item.data(0), item.parent())[key]


class TreeModel(QAbstractItemModel):
    def __init__(self, data, parent=None):
        super(TreeModel, self).__init__(parent)

        self.rootItem = DictTreeItem(data=data, key=None, parent=None)
        self.setupModelData(data, self.rootItem)

    def columnCount(self, parent=QModelIndex()):
        return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return None

        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None

        item = self.getItem(index)
        return item.data(index.column())

    def flags(self, index):
        if not index.isValid():
            return 0

        return Qt.ItemIsEditable | super(TreeModel, self).flags(index)

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self.rootItem

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.rootItem.data(section)

        return None

    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        parentItem = self.getItem(parent)
        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = self.getItem(index)
        parentItem = childItem.parent()

        if parentItem == self.rootItem:
            return QModelIndex()

        return self.createIndex(parentItem.childNumber(), 0, parentItem)

    def rowCount(self, parent=QModelIndex()):
        parentItem = self.getItem(parent)

        return parentItem.childCount()

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False

        item = self.getItem(index)
        result = item.setData(index.column(), value)

        if result:
            self.dataChanged.emit(index, index)

        return result

    def setHeaderData(self, section, orientation, value, role=Qt.EditRole):
        if role != Qt.EditRole or orientation != Qt.Horizontal:
            return False

        result = self.rootItem.setData(section, value)
        if result:
            self.headerDataChanged.emit(orientation, section, section)

        return result

    def setupModelData(self, data, parent):

        for key, value in data.items():
            parent.insertChild(parent.childCount(), data, key)

            if isinstance(value, dict):
                child = parent.child(parent.childCount() - 1)
                self.setupModelData(value, child)

