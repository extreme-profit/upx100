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
    password = forms.CharField(
        label='Пароль для ЛК',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Придумайте пароль'}),
        help_text='Оставьте пустым при редактировании, если не хотите менять пароль'
    )
    password_confirm = forms.CharField(
        label='Подтверждение пароля',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Подтвердите пароль'}),
        help_text='Повторите пароль'
    )
    
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # При создании сотрудника пароль обязателен
        if not self.instance.pk:
            self.fields['password'].required = True
            self.fields['password_confirm'].required = True
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.instance.pk and not password:
            raise forms.ValidationError('Пароль обязателен для нового сотрудника')
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Пароли не совпадают')
        
        return cleaned_data
    
    def save(self, commit=True):
        # При создании сотрудника сначала сохраняем без company, затем устанавливаем его
        if not self.instance.pk:
            # Это новый сотрудник - сохраняем с commit=False чтобы установить company
            employee = super().save(commit=False)
            password = self.cleaned_data.get('password')
            if password:
                # Хешируем пароль вручную, не вызывая save() внутри set_password
                from django.contrib.auth.hashers import make_password
                employee.password = make_password(password)
            # Не сохраняем здесь, это сделает view после установки company
            if commit:
                employee.save()
            return employee
        else:
            # Редактирование существующего
            employee = super().save(commit=commit)
            password = self.cleaned_data.get('password')
            if password:
                employee.set_password(password)
                if commit:
                    employee.save()
            return employee


class ServiceForm(forms.ModelForm):
    """Форма услуги"""
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        label='Категория',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    # Используем IntegerField вместо ModelChoiceField чтобы избежать проблемы с queryset
    # Валидацию подкатегории делаем вручную в clean_subcategory
    subcategory_id = forms.IntegerField(
        label='Подкатегория',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
        error_messages={
            'required': 'Выберите подкатегорию',
            'invalid': 'Выберите корректную подкатегорию',
        }
    )
    employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.none(),
        label='Сотрудники',
        required=True,
        widget=forms.CheckboxSelectMultiple(),
        help_text='Выберите одного или нескольких сотрудников, которые оказывают эту услугу'
    )
    
    class Meta:
        model = Service
        fields = ['name', 'description', 'price', 'duration', 'photo']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название услуги'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Описание услуги'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'В минутах'}),
        }
    
    def __init__(self, *args, **kwargs):
        # Получаем компанию из kwargs если есть
        self.company = kwargs.pop('company', None)
        
        # Получаем категорию ДО вызова super().__init__()
        category_id = None
        
        # Сначала пробуем получить из POST/GET данных
        if kwargs.get('data'):
            category_id = kwargs['data'].get('category')
        # Если редактируем существующий объект и категория не передана в data
        elif kwargs.get('instance') and kwargs['instance'].pk and kwargs['instance'].category_id:
            category_id = kwargs['instance'].category_id
        
        # Преобразуем в int если это строка
        if category_id and isinstance(category_id, str):
            try:
                category_id = int(category_id)
            except (ValueError, TypeError):
                category_id = None
        
        # Сохраняем ID категории для использования в clean_subcategory
        self._category_id = category_id
        
        # Получаем queryset для подкатегорий
        if category_id:
            self._subcategory_queryset = Subcategory.objects.filter(category_id=category_id)
        else:
            self._subcategory_queryset = Subcategory.objects.none()
        
        super().__init__(*args, **kwargs)
        
        # Настраиваем виджет subcategory_id с правильными options
        if category_id:
            subcategories = Subcategory.objects.filter(category_id=category_id)
            choices = [('', 'Выберите подкатегорию')] + [(sub.pk, sub.name) for sub in subcategories]
            self.fields['subcategory_id'].choices = choices
        else:
            self.fields['subcategory_id'].choices = [('', 'Сначала выберите категорию')]
        
        # Устанавливаем queryset для сотрудников только если есть компания
        if self.company:
            self.fields['employees'].queryset = self.company.employees.filter(is_active=True)
        else:
            self.fields['employees'].queryset = Employee.objects.none()
            
        self.fields['category'].empty_label = 'Выберите категорию'
        
        # Если редактируем существующую услугу, устанавливаем начальные значения
        if self.instance and self.instance.pk and self.instance.category_id:
            self.fields['category'].initial = self.instance.category_id
            # Устанавливаем начальное значение для subcategory_id
            if self.instance.subcategory_id:
                self.fields['subcategory_id'].initial = self.instance.subcategory_id
        elif kwargs.get('data') and kwargs['data'].get('category'):
            self.fields['category'].initial = kwargs['data'].get('category')
        
        # Если редактируем существующую услугу, загружаем выбранных сотрудников
        if self.instance and self.instance.pk:
            self.fields['employees'].initial = self.instance.employees.all()
    
    def clean_subcategory_id(self):
        """Проверка подкатегории: должна принадлежать выбранной категории"""
        subcategory_id = self.cleaned_data.get('subcategory_id')
        
        # Используем сохраненный ID категории из __init__
        category_id = getattr(self, '_category_id', None)
        
        # Если категория не была установлена в __init__, пробуем получить из cleaned_data
        if not category_id:
            category = self.cleaned_data.get('category')
            if category:
                category_id = category.id
        
        if not category_id:
            raise forms.ValidationError('Сначала выберите категорию')
        
        # Если подкатегория не выбрана - это ошибка
        if not subcategory_id:
            raise forms.ValidationError('Выберите подкатегорию')
        
        # Проверяем что подкатегория существует и принадлежит выбранной категории
        try:
            subcategory = Subcategory.objects.get(pk=subcategory_id)
        except Subcategory.DoesNotExist:
            raise forms.ValidationError('Выбранная подкатегория не существует')
        
        if int(subcategory.category_id) != int(category_id):
            raise forms.ValidationError('Выбранная подкатегория не относится к выбранной категории')
        
        # Сохраняем объект подкатегории для использования в save()
        self._subcategory_instance = subcategory
        
        return subcategory_id
    
    def clean(self):
        """Дополнительная очистка для синхронизации категории и подкатегории"""
        cleaned_data = super().clean()
        
        # Если есть и категория и подкатегория, убеждаемся что они совместимы
        category = cleaned_data.get('category')
        subcategory_id = cleaned_data.get('subcategory_id')
        
        if category and subcategory_id:
            try:
                subcategory = Subcategory.objects.get(pk=subcategory_id)
                if subcategory.category_id != category.id:
                    raise forms.ValidationError('Подкатегория должна относиться к выбранной категории')
            except Subcategory.DoesNotExist:
                raise forms.ValidationError('Выбранная подкатегория не существует')
        
        return cleaned_data
    
    def save(self, commit=True):
        """Сохранение услуги с правильной подкатегорией и сотрудниками"""
        service = super().save(commit=False)
        subcategory_id = self.cleaned_data.get('subcategory_id')
        category = self.cleaned_data.get('category')
        
        # Устанавливаем категорию и подкатегорию
        if category:
            service.category = category
        if hasattr(self, '_subcategory_instance'):
            service.subcategory = self._subcategory_instance
            
        if commit:
            service.save()
            # Сохраняем сотрудников через many-to-many
            employees = self.cleaned_data.get('employees')
            if employees is not None:
                service.employees.set(employees)
        return service


class PaymentForm(forms.ModelForm):
    """Форма оплаты"""
    class Meta:
        model = Payment
        fields = ['amount']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'readonly': True}),
        }
