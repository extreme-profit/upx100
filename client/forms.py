from django import forms


class BookingForm(forms.Form):
    slot_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    client_name = forms.CharField(max_length=150)
    client_phone = forms.CharField(max_length=20)
    client_email = forms.EmailField(max_length=254)
    notes = forms.CharField(required=False, widget=forms.Textarea)


class ReviewForm(forms.Form):
    rating = forms.TypedChoiceField(coerce=int, choices=[(n, f'{n} из 5') for n in range(5, 0, -1)], label='Оценка мастера')
    comment = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows':5}), label='Ваш отзыв')
