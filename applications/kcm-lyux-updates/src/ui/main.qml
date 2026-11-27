import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: root
    title: "Mises à jour LyuX"

    function compData(key) {
        var localMap = (kcm.stateData && kcm.stateData.local) ? kcm.stateData.local : ({})
        var policyMap = (kcm.stateData && kcm.stateData.policy) ? kcm.stateData.policy : ({})
        var pol = policyMap[key] || ({})
        return {
            local: localMap[key] || "Inconnue",
            selected: pol.selected_version || "Non définie par le serveur",
            latest: pol.latest_version || "Non vérifiée",
            hasSelected: Boolean(pol.selected_version && pol.selected_version.length > 0)
        }
    }

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: kcm.statusMessage.length > 0
            text: kcm.statusMessage
            type: Kirigami.MessageType.Information
        }

        Repeater {
            model: [
                { key: "debian", title: "Debian" },
                { key: "kde", title: "KDE Plasma" },
                { key: "lyux", title: "LyuX OS" }
            ]

            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                required property var modelData
                readonly property var info: root.compData(modelData.key)

                header: Kirigami.Heading {
                    text: modelData.title
                    level: 3
                }

                contentItem: Kirigami.FormLayout {
                    QQC2.Label {
                        Kirigami.FormData.label: "Dernière version existante :"
                        text: info.latest
                        font.family: "monospace"
                    }
                    QQC2.Label {
                        Kirigami.FormData.label: "Version sélectionnée par le serveur :"
                        text: info.selected
                        font.family: "monospace"
                        font.bold: true
                    }
                    QQC2.Label {
                        Kirigami.FormData.label: "Version sur cette machine :"
                        text: info.local
                        font.family: "monospace"
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            QQC2.Button {
                text: "Actualiser"
                icon.name: "view-refresh"
                enabled: !kcm.busy
                onClicked: kcm.refresh()
            }

            Item { Layout.fillWidth: true }

            QQC2.Button {
                text: "Mettre à jour vers la version validée par le serveur"
                icon.name: "system-software-update"
                enabled: !kcm.busy
                onClicked: kcm.applyUpdates()
            }
        }
    }
}
