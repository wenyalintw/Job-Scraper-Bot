from telegram.ext import Updater
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging
from telegram.ext import CommandHandler, CallbackQueryHandler
from telegram.ext import MessageHandler, Filters
import utils
from itertools import islice
import os
import json
import schedule as sd
import threading
import time
import confidential
import boto3
import requests


"""
Callback Function
"""

# Google Drive相關的callback
def drive(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=drive_msg)


def setdrive(update, context):
    # aws
    key_list = [content['Key'] for content in s3.list_objects(Bucket=confidential.Bucket)['Contents']]
    if f'user_credentials/{update.effective_chat.id}.json' in key_list:
    # local
    # if os.path.isfile(f'user_credentials/{update.effective_chat.id}.json'):
        context.bot.send_message(chat_id=update.effective_chat.id, text='您已授權過機器人囉！')
        return

    authorize_url = utils.get_authorize_url()
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=f'請點擊連結完成授權，並回傳"/code <產生的授權碼>"，例如：\n'
                             f'/code abc123\n{authorize_url}\n')


def code(update, context):
    auth_code = context.args[0]
    msg = utils.save_drive_credential(chat_id=update.effective_chat.id, code=auth_code, s3=s3)
    context.bot.send_message(chat_id=update.effective_chat.id, text=msg)


def unsetdrive(update, context):
    try:
        # aws
        s3.delete_object(Bucket='job-scraper-bot-bucket', Key=f'user_credentials/{update.effective_chat.id}.json')
        # local
        # os.remove(f'user_credentials/{update.effective_chat.id}.json')
        context.bot.send_message(chat_id=update.effective_chat.id, text='已取消授權！')
    except Exception as e:
        context.bot.send_message(chat_id=update.effective_chat.id, text='您還沒設定授權哦！')


# start
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=help_msg,
                             parse_mode='HTML', disable_web_page_preview=True)


# 推播管理相關callback
def list(update, context):
    keywords = have_keywords(update, context)
    if keywords:
        context.bot.send_message(chat_id=update.effective_chat.id, text='您目前推播的搜尋關鍵字有：\n'+'\n'.join(keywords))


def delete(update, context):
    keywords = have_keywords(update, context)
    if keywords:
        keyboard = [[InlineKeyboardButton(keyword, callback_data=i)] for i, keyword in enumerate(keywords)]
        reply_markup = InlineKeyboardMarkup(keyboard)

        context.bot.send_message(chat_id=update.effective_chat.id, text='請選取要取消推播的關鍵字', reply_markup=reply_markup)


def button(update, context):
    index = int(user_data[str(update.effective_chat.id)])
    query = update.callback_query
    keyword, push_time = user_data['users'][index]['keywords'][int(query.data)]
    user_data['users'][index]['keywords'].pop(int(query.data))
    update_user_data(update.effective_chat.id, None, None)

    sd.clear(f'{update.effective_chat.id}_{keyword}_{push_time}')

    query.answer()
    query.edit_message_text(text=f'已刪除【{keyword} @{push_time}】')


# 搜尋與推播關鍵字設定等
def search(update, context):
    if context.args == []:
        context.bot.send_message(chat_id=update.effective_chat.id, text='請在 /search 後輸入搜尋關鍵字')
        return

    keyword = ' '.join(context.args)
    bot.send_message(chat_id=chat_id, text=f'正在爬取【{keyword}】，請稍待...\n')
    csv_data = utils.scrap(keyword, update.effective_chat.id, s3=s3)

    if csv_data.__len__() == 0:
        context.bot.send_message(chat_id=update.effective_chat.id, text='此關鍵字今日無更新職缺')
    else:
        for job in islice(csv_data, 1, None):
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     disable_web_page_preview=True, text='\n'.join(job))


def schedule(update, context):
    try:
        keyword, push_time = map(str.strip, ' '.join(context.args).split('@'))
    except:
        unknown(update, context)
        return

    try:
        sd.every().day.at(push_time).do(push, update.effective_chat.id, keyword).tag(
            f'{update.effective_chat.id}_{keyword}_{push_time}')

        update_user_data(update.effective_chat.id, keyword, push_time)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=f'成功加入推播列表！\n機器人將在每日{push_time}推播爬取【{keyword}】之資訊給您')
    except Exception as e:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=f'時間格式有誤哦！請重新輸入\n格式為24小時制，缺空須補0，如09:05')


# 看不懂的訊息
def unknown(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text='機器人看不懂您說什麼\n請用 /help 觀看使用說明')


"""
Other Function
"""


# 上面放callback func，下面放一般func
def have_keywords(update, context):
    try:
        index = int(user_data[str(update.effective_chat.id)])
    except Exception as e:
        context.bot.send_message(chat_id=update.effective_chat.id, text="您目前沒有排程任何關鍵字")
        return None
    keywords = user_data['users'][index]['keywords']
    if keywords.__len__() == 0:
        context.bot.send_message(chat_id=update.effective_chat.id, text="您目前沒有排程任何關鍵字")
        return None

    keywords_to_display = [f'{d[0]} @{d[1]}' for d in keywords]

    return keywords_to_display


def push(chat_id, keyword):
    bot.send_message(chat_id=chat_id, text=f'正在爬取【{keyword}】，請稍待...\n')
    csv_data = utils.scrap(keyword, chat_id, s3=s3)
    if csv_data.__len__() == 0:
        bot.send_message(chat_id=chat_id, text=f'關鍵字【{keyword}】今日無更新職缺')
    else:
        for job in islice(csv_data, 1, None):
            bot.send_message(chat_id=chat_id, disable_web_page_preview=True,
                                     text='\n'.join(job))


def update_user_data(chat_id, keyword, push_time):

    if keyword:
        user_exist = False
        for i, user in enumerate(user_data['users']):
            if chat_id == user['chat_id']:
                user_data['users'][i]['keywords'].append([keyword, push_time])
                user_exist = True
                break
        if not user_exist:
            user_data['users'].append({'chat_id': chat_id, 'keywords': [[keyword, push_time]]})
            user_data[str(chat_id)] = str(user_data['users'].__len__() - 1)

    # aws
    s3.put_object(Bucket=confidential.Bucket, Key=user_data_filename, Body=json.dumps(user_data, indent=2))
    # local
    # with open(user_data_filename, 'w') as json_file:
    #     json.dump(user_data, json_file, indent=2)


def schdule_threading():
    minutes = 0
    while True:
        sd.run_pending()
        print([job.tags for job in sd.jobs])
        # print(sd.jobs)
        # 每分鐘check一下有沒有pending的要跑
        time.sleep(60)
        minutes += 1
        # 避免heroku把dyno休眠
        if minutes % 25 == 0 and deploy_on_heroku:
            print(requests.get(f'https://{heroku_appname}.herokuapp.com/'))


def reschedule(user_data):
    for user in user_data['users']:
        chat_id = user['chat_id']
        for keywords in user['keywords']:
            keyword = keywords[0]
            push_time = keywords[1]
            sd.every().day.at(push_time).do(push, chat_id, keyword).tag(f'{chat_id}_{keyword}_{push_time}')


if __name__ == '__main__':

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    job_scraper_bot_token = confidential.job_scraper_bot_token

    s3 = boto3.client('s3', aws_access_key_id=confidential.ACCESS_KEY_ID,
                      aws_secret_access_key=confidential.SECRET_ACCESS_KEY)

    help_msg = '歡迎使用104職缺推播機器人，機器人會根據您提供的搜尋關鍵字，從104網站爬取當日更新的第一頁職缺給您！\n' \
               '具<b>每日推播</b>與<b>自動上傳Google Drive</b>功能，以下為使用說明：\n' \
               '\n<b>搜尋與推播設定</b>\n' \
               '/search 行銷 企劃 - 直接搜尋關鍵字【行銷 企劃】\n' \
               '/schedule 半導體 @22:30 - 將於每日22:30推播【半導體】職缺給您\n' \
               '<b>管理您的推播列表</b>\n' \
               '/list - 列出推播列表\n' \
               '/delete - 選取關鍵字並刪除\n' \
               '<b>Google Drive設定</b>' \
               '\n/drive - 觀看如何設定\n' \
               '\n/help - 呼叫此說明' \
               '\n\u00a9 <a href="https://wenyalintw.github.io">Wen-Ya Lin</a>'

    drive_msg = '應朋友要求弄的小功能XD，可以將每次的搜尋結果存成.csv檔上傳到Google Drive上，建議使用Excel開啟！\n' \
                '\n/setdrive - 授權您的Google Drive權限給機器人，僅需授權一次\n' \
                '/unsetdrive - 取消授權\n' \
                '\n授權成功後，機器人會在您的Google Drive上建立名為『104職缺推播機器人』的資料夾，並把結果存進去！'

    # aws
    try:
        key_list = [content['Key'] for content in s3.list_objects(Bucket=confidential.Bucket)['Contents']]
    except Exception as e:
        key_list = []
    if 'user_credentials/' not in key_list:
        s3.put_object(Bucket=confidential.Bucket, Key='user_credentials/')
    # local
    # os.makedirs('user_credentials', exist_ok=True)

    # user_data
    # aws
    user_data_filename = 'user_data.json'
    if user_data_filename not in key_list:
        initial_json = {'users': []}
        # json.dump ≠ json.dumps
        s3.put_object(Bucket=confidential.Bucket, Key=user_data_filename, Body=json.dumps(initial_json, indent=2))
    obj = s3.get_object(Bucket='job-scraper-bot-bucket', Key='user_data.json')
    user_data = json.loads(obj['Body'].read())

    # local
    # if not os.path.exists(user_data_filename):
    #     with open(user_data_filename, 'w') as json_file:
    #         initial_json = {'users': []}
    #         json.dump(initial_json, json_file, indent=2)
    # with open(user_data_filename, 'r') as f:
    #     user_data = json.load(f)

    reschedule(user_data=user_data)

    updater = Updater(token=job_scraper_bot_token, use_context=True)
    dispatcher = updater.dispatcher
    # 用來處理reschedule要用到push的bot辨認問題，因此程式只連結到一個bot，統一用這個就好（所有的context.bot都可以改這個也沒差）
    bot = updater.bot

    # special
    special_handler = CommandHandler('special', special)
    dispatcher.add_handler(special_handler)

    # dispatch設定
    # 開始與幫助指令
    start_handler = CommandHandler('start', start)
    dispatcher.add_handler(start_handler)
    help_handler = CommandHandler('help', start)
    dispatcher.add_handler(help_handler)

    # 直接搜尋指令
    search_handler = CommandHandler('search', search)
    dispatcher.add_handler(search_handler)

    # 推播相關指令
    schedule_handler = CommandHandler('schedule', schedule)
    dispatcher.add_handler(schedule_handler)
    list_handler = CommandHandler('list', list)
    dispatcher.add_handler(list_handler)
    delete_handler = CommandHandler('delete', delete)
    dispatcher.add_handler(delete_handler)
    updater.dispatcher.add_handler(CallbackQueryHandler(button))

    # Google Drive相關指令
    drive_handler = CommandHandler('drive', drive)
    dispatcher.add_handler(drive_handler)
    setdrive_handler = CommandHandler('setdrive', setdrive)
    dispatcher.add_handler(setdrive_handler)
    unsetdrive_handler = CommandHandler('unsetdrive', unsetdrive)
    dispatcher.add_handler(unsetdrive_handler)

    code_handler = CommandHandler('code', code)
    dispatcher.add_handler(code_handler)

    # 看不懂的指令
    unknown_handler = MessageHandler(Filters.text | Filters.command, unknown)
    dispatcher.add_handler(unknown_handler)

    # 設定排程的那些搜尋
    schedule_thread = threading.Thread(target=schdule_threading).start()

    deploy_on_heroku = True
    heroku_port = os.environ.get('PORT')
    heroku_appname = confidential.heroku_appname
    if deploy_on_heroku:
        # 在heroku跑
        updater.start_webhook(listen='0.0.0.0', port=int(heroku_port), url_path=job_scraper_bot_token)
        updater.bot.setWebhook(f'https://{heroku_appname}.herokuapp.com/{job_scraper_bot_token}')
    else:
        # 在lcoal電腦跑
        updater.start_polling()
    updater.idle()
