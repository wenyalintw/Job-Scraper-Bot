import requests
import bs4
import time
import csv
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import os
import boto3
import confidential
import json

def scrap(keyword, chat_id, s3):
    """
    爬取網頁並回傳csv data
    """
    # aws
    key_list = [content['Key'] for content in s3.list_objects(Bucket=confidential.Bucket)['Contents']]
    have_setdrive = f'user_credentials/{chat_id}.json' in key_list
    # local
    # have_setdrive = os.path.isfile(f'user_credentials/{chat_id}.json')

    if have_setdrive:
        excel_csv_data = [['職缺名稱', '公司名稱', '地區', '經歷', '學歷', '薪資', '工作內容']]

    csv_data = []

    # '半導體 設備'.replace(' ', '%20')
    # 設定isnew=0本日最新、keyword就好，其他用預設
    url_base = f'https://www.104.com.tw/jobs/search/?isnew=0&keyword={keyword.replace(" ", "%20")}'
    # 把輸入的空格換成%20即可
    how_many_pages = 1
    for page in range(1, how_many_pages + 1):

        if page > 1:
            time.sleep(2)

        url = url_base + f'&page={page}'
        htmlFile = requests.get(url)
        ObjSoup = bs4.BeautifulSoup(htmlFile.text, 'lxml')
        jobs = ObjSoup.find_all('article', class_='js-job-item')  # 搜尋所有職缺

        for job in jobs:
            # 為了地區/經歷/學歷
            temp = job.find('ul', class_='job-list-intro').text.split('\n\n')
            link = 'https:' + job.find('a').get('href')
            job_name = job.get('data-job-name')
            company_name = job.get('data-cust-name')
            location = temp[0].strip('\n')
            experience = temp[1]
            education = temp[2].strip('\n')
            salary = job.find('span', class_='b-tag--default').text
            try:
                job_description = job.find('p', class_='job-list-item__info').text.replace('\r', '')
            except Exception as e:
                job_description = '此職缺沒有職缺介紹'

            csv_data.append([link, job_name, company_name, f'{location}/{experience}/{education}',
                             salary, job_description])

            if have_setdrive:
                excel_csv_data.append([f'=HYPERLINK("{link}","{job_name}")', company_name,
                                   location, experience, education, salary,job_description])

    if have_setdrive:
    # if os.path.isfile(f'{chat_id}.json'):
        write_csv(excel_csv_data)
        upload_drive(keyword, chat_id, s3)

    return csv_data


def write_csv(csv_data):
    with open('temp.csv', 'w', encoding='utf-8-sig', errors='replace') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(csv_data)


def get_authorize_url():
    gauth = GoogleAuth()
    return gauth.GetAuthUrl()


def save_drive_credential(chat_id, code, s3):
    try:
        gauth = GoogleAuth()
        gauth.Auth(code)
        gauth.SaveCredentialsFile(f'{chat_id}.json')
        s3.upload_file(Filename=f'{chat_id}.json', Bucket=confidential.Bucket, Key=f'user_credentials/{chat_id}.json')
        return '授權成功！'
    except Exception as e:
        return '授權失敗！可能是格式錯了之類的QQ，麻煩再試一次'


def upload_drive(keyword, chat_id, s3):
    # 先從aws抓credential檔，這邊做法很笨，待改進
    obj = s3.get_object(Bucket=confidential.Bucket, Key=f'user_credentials/{chat_id}.json')
    with open(f'{chat_id}.json', 'w') as json_file:
        json.dump(json.loads(obj['Body'].read()), json_file, indent=2)

    gauth = GoogleAuth()
    gauth.LoadCredentialsFile(f'{chat_id}.json')
    drive = GoogleDrive(gauth)

    # check folder是否已存在
    folder_name = '104職缺推播機器人'
    folder_id = None
    folder_list = drive.ListFile({'q': "mimeType = 'application/vnd.google-apps.folder' and trashed = false"}).GetList()
    for folder in folder_list:
        if folder['title'] == folder_name:
            folder_id = folder['id']
            break

    if not folder_id:
        folder = drive.CreateFile({'title': folder_name, 'mimeType': 'application/vnd.google-apps.folder'})
        folder.Upload()
        folder_id = folder['id']

    date = '_'.join(map(str, time.localtime()[0:3]))
    filename = f'{date}_{keyword}.csv'

    # lcoal永遠都存temp.csv，上傳到雲端的再有custom filename
    file = drive.CreateFile({'title': filename, 'parents': [{'kind': 'drive#fileLink', 'id': folder_id}]})
    file.SetContentFile(filename='temp.csv')
    file.Upload()
