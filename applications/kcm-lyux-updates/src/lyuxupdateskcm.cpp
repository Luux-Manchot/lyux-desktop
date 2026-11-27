#include "lyuxupdateskcm.h"

#include <KPluginFactory>
#include <QJsonDocument>
#include <QJsonObject>

K_PLUGIN_CLASS_WITH_JSON(LyuxUpdatesKcm, "kcm_lyux_updates.json")

LyuxUpdatesKcm::LyuxUpdatesKcm(QObject *parent, const KPluginMetaData &data)
    : KQuickConfigModule(parent, data)
{
    setButtons(NoAdditionalButton);
    refresh();
}

void LyuxUpdatesKcm::refresh()
{
    if (m_busy) {
        return;
    }
    m_busy = true;
    Q_EMIT busyChanged();
    m_statusMessage = QStringLiteral("Lecture des versions locales et de la politique serveur...");
    Q_EMIT statusMessageChanged();

    auto *proc = new QProcess(this);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this,
        [this, proc](int exitCode, QProcess::ExitStatus) {
            const QByteArray out = proc->readAllStandardOutput();
            const QByteArray err = proc->readAllStandardError();
            proc->deleteLater();

            m_busy = false;
            Q_EMIT busyChanged();

            if (exitCode == 0) {
                const QJsonDocument doc = QJsonDocument::fromJson(out);
                if (doc.isObject()) {
                    m_stateData = doc.object().toVariantMap();
                    Q_EMIT stateDataChanged();
                    const QVariantMap policy = m_stateData.value(QStringLiteral("policy")).toMap();
                    m_statusMessage = policy.isEmpty()
                        ? QStringLiteral("Serveur LyuX non joignable ou poste non enrôlé.")
                        : QStringLiteral("Politique serveur synchronisée.");
                    Q_EMIT statusMessageChanged();
                    return;
                }
            }
            m_statusMessage = QString::fromUtf8(err.isEmpty() ? out : err).trimmed();
            if (m_statusMessage.isEmpty()) {
                m_statusMessage = QStringLiteral("Impossible de lire l'état des mises à jour.");
            }
            Q_EMIT statusMessageChanged();
        });

    proc->start(QStringLiteral("python3"), {
        QStringLiteral("/opt/lyux/apps/enrollment/src/update_policy_sync.py"),
        QStringLiteral("--json")
    });
}

void LyuxUpdatesKcm::applyUpdates()
{
    if (m_busy) {
        return;
    }
    m_busy = true;
    Q_EMIT busyChanged();
    m_statusMessage = QStringLiteral("Application des mises à jour validées par le serveur en cours...");
    Q_EMIT statusMessageChanged();

    auto *proc = new QProcess(this);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this,
        [this, proc](int exitCode, QProcess::ExitStatus) {
            const QString out = QString::fromUtf8(proc->readAllStandardOutput()).trimmed();
            const QString err = QString::fromUtf8(proc->readAllStandardError()).trimmed();
            proc->deleteLater();

            m_busy = false;
            Q_EMIT busyChanged();

            if (exitCode == 0) {
                m_statusMessage = out.isEmpty()
                    ? QStringLiteral("Mises à jour validées appliquées avec succès.")
                    : out;
            } else {
                m_statusMessage = err.isEmpty()
                    ? (out.isEmpty() ? QStringLiteral("Échec de l'application des mises à jour.") : out)
                    : err;
            }
            Q_EMIT statusMessageChanged();
            refresh();
        });

    proc->start(QStringLiteral("pkexec"), {
        QStringLiteral("/opt/lyux/apps/enrollment/scripts/lyux-apply-updates.sh")
    });
}

#include "lyuxupdateskcm.moc"
