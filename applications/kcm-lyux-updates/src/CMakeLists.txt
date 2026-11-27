kcmutils_add_qml_kcm(kcm_lyux_updates)

target_sources(kcm_lyux_updates PRIVATE
    lyuxupdateskcm.cpp
    lyuxupdateskcm.h
)

target_link_libraries(kcm_lyux_updates PRIVATE
    Qt::Quick
    KF6::CoreAddons
    KF6::KCMUtils
    KF6::I18n
)
