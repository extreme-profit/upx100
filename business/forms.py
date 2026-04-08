from django import forms
from .models import Company, Employee, Service, Payment
from companies.models import Category, Subcategory


class CompanyForm(forms.ModelForm):
    """Форма профиля компании"""
    class Meta:
        model = Company
        fields = ['name', 'description', 'logo', 'photo', 'address', 'latitude', 'longitude']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название компании'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Описание компании'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Адрес'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
        }


class EmployeeForm(forms.ModelForm):
    """Форма сотрудника"""
    class Meta:
        model = Employee
        fields = ['name', 'position', 'phone', 'email', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ФИО сотрудника'}),
            'position': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Должность'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+7 (___) ___-__-__'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ServiceForm(forms.ModelForm):
    """Форма услуги"""
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        label='Категория',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    subcategory_id = forms.IntegerField(
        label='Подкатегория',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Service
        fields = ['name', 'description', 'price', 'duration', 'photo', 'employee']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название услуги'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Описание услуги'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'В минутах'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].empty_label = 'Выберите сотрудника'
        self.fields['employee'].queryset = Employee.objects.none()  # Будет переопределено в view
        self.fields['category'].empty_label = 'Выберите категорию'
        self.fields['subcategory_id'].empty_label = 'Сначала выберите категорию'
        
        # Получаем категорию из данных формы (при POST) или из начальных значений
        category_id = None
        
        # Сначала пробуем получить из POST/GET данных
        if kwargs.get('data'):
            category_id = kwargs['data'].get('category')
        # Если нет в data, пробуем initial
        elif kwargs.get('initial') and kwargs['initial'].get('category'):
            cat = kwargs['initial']['category']
            category_id = cat.pk if hasattr(cat, 'pk') else cat
        # Если редактируем существующий объект
        elif self.instance and self.instance.pk and self.instance.category_id:
            category_id = self.instance.category_id
        
        # Преобразуем в int если это строка
        if category_id and isinstance(category_id, str):
            try:
                category_id = int(category_id)
            except (ValueError, TypeError):
                category_id = None
        
        # Устанавливаем choices для подкатегорий на основе категории
        if category_id:
            subcategories = Subcategory.objects.filter(category_id=category_id)
            self.fields['subcategory_id'].choices = [('', 'Выберите подкатегорию')] + [(sub.id, sub.name) for sub in subcategories]
            # Если есть начальное значение подкатегории, устанавливаем его
            if self.instance and self.instance.pk and self.instance.subcategory_id:
                self.fields['subcategory_id'].initial = self.instance.subcategory_id
            elif kwargs.get('data') and kwargs['data'].get('subcategory_id'):
                # Сохраняем выбранную подкатегорию из POST данных
                self.fields['subcategory_id'].initial = kwargs['data'].get('subcategory_id')
        
        # Если редактируем существующую услугу, устанавливаем начальные значения
        if self.instance and self.instance.pk and self.instance.category_id:
            self.fields['category'].initial = self.instance.category_id
        elif kwargs.get('data') and kwargs['data'].get('category'):
            self.fields['category'].initial = kwargs['data'].get('category')
    
    def clean_subcategory_id(self):
        """Проверка подкатегории: должна принадлежать выбранной категории"""
        subcategory_id = self.cleaned_data.get('subcategory_id')
        category = self.cleaned_data.get('category')
        
        if not subcategory_id:
            raise forms.ValidationError('Выберите подкатегорию')
        
        if not category:
            raise forms.ValidationError('Сначала выберите категорию')
        
        # Проверяем что подкатегория существует и принадлежит категории
        try:
            subcategory = Subcategory.objects.get(id=subcategory_id, category_id=category.id)
        except Subcategory.DoesNotExist:
            raise forms.ValidationError('Выберите корректный вариант. Вашего варианта нет среди допустимых значений.')
        
        return subcategory_id
    
    def save(self, commit=True):
        """Сохранение услуги с правильной подкатегорией"""
        service = super().save(commit=False)
        subcategory_id = self.cleaned_data.get('subcategory_id')
        if subcategory_id:
            service.subcategory_id = subcategory_id
        if commit:
            service.save()
        return service


class PaymentForm(forms.ModelForm):
    """Форма оплаты"""
    class Meta:
        model = Payment
        fields = ['amount']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'readonly': True}),
        }
