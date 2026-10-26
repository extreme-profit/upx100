from django import forms
from .security import valid_phone, public_ip


class FraudBlockForm(forms.Form):
    reason = forms.CharField(label='Причина подтверждённого нарушения', max_length=4000, widget=forms.Textarea(attrs={'rows':3}))
    evidence = forms.CharField(label='Материалы проверки, номера заявок и обращений', max_length=10000, required=False, widget=forms.Textarea(attrs={'rows':4}))
    extra_phones = forms.CharField(label='Дополнительные подтверждённые телефоны — по одному в строке', max_length=4000, required=False, widget=forms.Textarea(attrs={'rows':2}))
    extra_ips = forms.CharField(label='Дополнительные подтверждённые публичные IP — по одному в строке', max_length=4000, required=False, widget=forms.Textarea(attrs={'rows':2}))
    block_ips = forms.BooleanField(label='Блокировать повторные регистрации с сохранённых публичных IP', required=False, initial=True)
    confirmed = forms.BooleanField(label='Факт нарушения проверен; подтверждаю бессрочное ограничение публикации')

    def clean_extra_phones(self):
        values = [v.strip() for v in self.cleaned_data['extra_phones'].splitlines() if v.strip()]
        if any(not valid_phone(value) for value in values):
            raise forms.ValidationError('Телефон должен содержать от 10 до 15 цифр.')
        return values

    def clean_extra_ips(self):
        values = [v.strip() for v in self.cleaned_data['extra_ips'].splitlines() if v.strip()]
        if any(not public_ip(value) for value in values):
            raise forms.ValidationError('Укажите корректные публичные IP; локальные и внутренние адреса не подходят.')
        return values
