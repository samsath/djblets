PIPELINE_JAVASCRIPT = {
    'djblets-avatars-config': {
        'source_filenames': (
            'djblets/js/avatars/base.js',
            'djblets/js/avatars/models/avatarSettingsModel.es6.js',
            'djblets/js/avatars/views/avatarServiceSettingsFormView.es6.js',
            'djblets/js/avatars/views/avatarSettingsFormView.es6.js',
            'djblets/js/avatars/views/fileUploadSettingsFormView.es6.js',
        ),
        'output_filename': 'djblets/js/avatars-config.min.js',
    },
    'djblets-config-forms': {
        'source_filenames': (
            'djblets/js/configForms/base.js',
            'djblets/js/configForms/collections/listItemsCollection.js',
            'djblets/js/configForms/models/listItemModel.js',
            'djblets/js/configForms/models/listModel.js',
            'djblets/js/configForms/views/listItemView.js',
            'djblets/js/configForms/views/listView.js',
            'djblets/js/configForms/views/pagesView.js',
            'djblets/js/configForms/views/tableItemView.js',
            'djblets/js/configForms/views/tableView.js',
        ),
        'output_filename': 'djblets/js/config-forms.min.js',
    },
    'djblets-datagrid': {
        'source_filenames': ('djblets/js/datagrid.js',),
        'output_filename': 'djblets/js/datagrid.min.js',
    },
    'djblets-extensions-admin': {
        'source_filenames': (
            'djblets/js/extensions/models/extensionManagerModel.js',
            'djblets/js/extensions/views/extensionManagerView.js',
        ),
        'output_filename': 'djblets/js/extensions-admin.min.js',
    },
    'djblets-extensions': {
        'source_filenames': (
            'djblets/js/extensions/base.js',
            'djblets/js/extensions/models/extensionModel.js',
            'djblets/js/extensions/models/extensionHookModel.js',
            'djblets/js/extensions/models/extensionHookPointModel.js',
        ),
        'output_filename': 'djblets/js/extensions.min.js',
    },
    'djblets-forms': {
        'source_filenames': (
            'djblets/js/forms/base.js',
            'djblets/js/forms/models/conditionChoiceModel.es6.js',
            'djblets/js/forms/models/conditionModel.es6.js',
            'djblets/js/forms/models/conditionOperatorModel.es6.js',
            'djblets/js/forms/models/conditionSetModel.es6.js',
            'djblets/js/forms/models/conditionValueField.es6.js',
            'djblets/js/forms/views/baseConditionValueFieldView.es6.js',
            'djblets/js/forms/views/conditionSetView.es6.js',
            'djblets/js/forms/views/conditionValueFormFieldView.es6.js',
            'djblets/js/forms/views/listEditView.es6.js',
        ),
        'output_filename': 'djblets/js/forms.min.js',
    },
    'djblets-gravy': {
        'source_filenames': (
            # These are in dependency order
            'djblets/js/jquery.gravy.util.js',
            'djblets/js/jquery.gravy.retina.js',
            'djblets/js/jquery.gravy.autosize.js',
            'djblets/js/jquery.gravy.inlineEditor.js',
            'djblets/js/jquery.gravy.modalBox.js',
            'djblets/js/jquery.gravy.tooltip.js',
            'djblets/js/jquery.gravy.funcQueue.js',
            'djblets/js/jquery.gravy.backboneUtils.js',
        ),
        'output_filename': 'djblets/js/jquery.gravy.min.js',
    },
    'djblets-js-tests': {
        'source_filenames': (
            'djblets/js/tests/backboneUtilsTests.js',
            'djblets/js/configForms/models/tests/listItemModelTests.js',
            'djblets/js/configForms/views/tests/listItemViewTests.js',
            'djblets/js/configForms/views/tests/listViewTests.js',
            'djblets/js/configForms/views/tests/tableItemViewTests.js',
            'djblets/js/configForms/views/tests/tableViewTests.js',
            'djblets/js/forms/models/tests/conditionChoiceModelTests.es6.js',
            'djblets/js/forms/models/tests/conditionModelTests.es6.js',
            'djblets/js/forms/models/tests/conditionOperatorModelTests.es6.js',
            'djblets/js/forms/models/tests/conditionSetModelTests.es6.js',
            'djblets/js/forms/views/tests/conditionSetViewTests.es6.js',
            'djblets/js/forms/views/tests/conditionValueFormFieldViewTests.es6.js',
            'djblets/js/forms/views/tests/listEditViewTests.es6.js',
        ),
        'output_filename': 'djblets/js/tests.min.js',
    },
    'djblets-utils': {
        'source_filenames': (
            'djblets/js/utils/promise.es6.js',
        ),
        'output_filename': 'djblets/js/utils.min.js',
    },
}


PIPELINE_STYLESHEETS = {
    'djblets-avatars-config': {
        'source_filenames': (
            'djblets/css/avatars.less',
        ),
        'output_filename': 'djblets/css/avatars-config.min.css',
    },
    'djblets-admin': {
        'source_filenames': (
            'djblets/css/admin.less',
            'djblets/css/extensions.less',
        ),
        'output_filename': 'djblets/css/admin.min.css',
    },
    'djblets-forms': {
        'source_filenames': (
            'djblets/css/forms/conditions.less',
            'djblets/css/forms/copyable_text_input.less',
            'djblets/css/forms/list_edit.less',
        ),
        'output_filename': 'djblets/css/forms.min.css',
    },
    'djblets-config-forms': {
        'source_filenames': (
            'djblets/css/config-forms.less',
        ),
        'output_filename': 'djblets/css/config-forms.min.css',
    },
    'djblets-datagrid': {
        'source_filenames': (
            'djblets/css/datagrid.less',
        ),
        'output_filename': 'djblets/css/datagrid.min.css',
    },
    'djblets-integrations': {
        'source_filenames': (
            'djblets/css/integrations.less',
        ),
        'output_filename': 'djblets/css/integrations.min.css',
    },
}
