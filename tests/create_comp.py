import ocmcli as ocm


def build_application(app: ocm.OcmApplication):
    app.clean()
    app.makedirs()
    # dyn_settings_file = str(app.gen_dir / 'dynamic_settings.yaml')
    # write_dynamic_settings_file(app, dyn_settings_file)
    app.create_ctf_from_spec(
        components_file_name='components.yaml',
        settings_files=['static_settings.yaml'],
    )
    app.descriptor()


def get_comp_descr(app: ocm.OcmApplication):
    app.descriptor()