from django.db import models

class ListOverview(models.Model):
    id= models.AutoField(auto_created=True, 
                            primary_key=True, 
                            serialize=False, 
                            verbose_name='ID')

    title= models.CharField(max_length=1000, 
                            verbose_name='title',
                            blank=True)

    content= models.CharField(max_length=5000, 
                                verbose_name='content',
                                blank=True)

    url= models.CharField(error_messages={'unique': 'A URL already exists.'},
                            max_length=250, 
                            unique=True, 
                            verbose_name='url',
                            blank=True)

    date= models.CharField(blank=True, 
                            max_length=30, 
                            verbose_name='date')

    category= models.CharField(blank=True, 
                                max_length=500, 
                                verbose_name='category')

    hashed = models.CharField(blank=True, 
                                max_length=254, 
                                verbose_name='hashed')

    page = models.CharField(blank=True, 
                                max_length=254, 
                                verbose_name='page')

    page_number = models.CharField(blank=True, 
                                max_length=100, 
                                verbose_name='page_number')

    crawled= models.BooleanField(default=False, 
                                    verbose_name='crawled')

    status= models.BooleanField(default=True, 
                                    verbose_name='status')

    image_url= models.CharField(error_messages={'unique': 'A URL already exists.'},
                                max_length=250, 
                                verbose_name='image_url',
                                blank=True)

    created_date = models.DateField(auto_now_add=True)
    updated_date = models.DateField(auto_now=True)



    def __str__(self):
        return str(self.title)

class CommandLog(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    type = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    started_at = models.DateTimeField(blank=True, null=True, db_index=True)
    ended_at = models.DateTimeField(blank=True, null=True, db_index=True)
    status = models.CharField(max_length=15, blank=True, null=True, db_index=True)
    message = models.TextField(blank=True, null=True)
