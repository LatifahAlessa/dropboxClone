from django import forms


class FileUploadForm(forms.Form):
    file = forms.FileField()
    current_path = forms.CharField(required=False, max_length=500)


class CreateFolderForm(forms.Form):
    folder_name = forms.CharField(max_length=255)
    current_path = forms.CharField(required=False, max_length=500)


class RenameFileForm(forms.Form):
    new_name = forms.CharField(max_length=255)
    current_path = forms.CharField(required=False, max_length=500)
