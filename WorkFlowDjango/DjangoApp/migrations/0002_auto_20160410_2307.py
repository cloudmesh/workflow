# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2016-04-11 03:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('DjangoApp', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='node_data',
            name='id',
        ),
        migrations.AlterField(
            model_name='node_data',
            name='node_name',
            field=models.CharField(max_length=100, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='node_data',
            name='updated',
            field=models.DateTimeField(auto_now=True),
        ),
    ]