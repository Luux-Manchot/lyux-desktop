#pragma once

#include <KQuickConfigModule>
#include <QProcess>
#include <QVariantMap>

class LyuxUpdatesKcm : public KQuickConfigModule
{
    Q_OBJECT
    Q_PROPERTY(QVariantMap stateData READ stateData NOTIFY stateDataChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString statusMessage READ statusMessage NOTIFY statusMessageChanged)

public:
    LyuxUpdatesKcm(QObject *parent, const KPluginMetaData &data);

    QVariantMap stateData() const { return m_stateData; }
    bool busy() const { return m_busy; }
    QString statusMessage() const { return m_statusMessage; }

    Q_INVOKABLE void refresh();
    Q_INVOKABLE void applyUpdates();

Q_SIGNALS:
    void stateDataChanged();
    void busyChanged();
    void statusMessageChanged();

private:
    QVariantMap m_stateData;
    bool m_busy = false;
    QString m_statusMessage;
};
