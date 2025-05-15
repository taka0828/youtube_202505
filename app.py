#!pip install streamlit # この行は通常、requirements.txtに記述し、app.pyからは削除します

from apiclient.discovery import build # google-api-python-client を使う場合
# from googleapiclient.discovery import build # より推奨されるインポート
import json # secret.json を使わないのであれば不要になる可能性
import pandas as pd
import streamlit as st

# secret.json の読み込み部分は削除 (Streamlit Community Cloudではst.secretsを使用)
# with open('secret.json') as f:
#     secret = json.load(f)

# Streamlit Community Cloudの「Secrets」からAPI keyを取得
try:
    developer_key = st.secrets["developer_key"] # キー名をsecretsで設定したものに合わせる
except KeyError:
    st.error("Streamlit Secretsに 'developer_key' が設定されていません。")
    st.stop() # APIキーがない場合はアプリを停止

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# youtubeオブジェクトを初期化
try:
    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                  developerKey=developer_key)
except Exception as e:
    st.error(f"YouTube APIクライアントの初期化に失敗しました: {e}")
    st.stop()

# --- 以降の関数定義 (video_search, get_results) は変更なしでOK ---
def video_search(youtube, q='自動化', max_results=50):
    # ... (既存のコード)
response = Youtube().list(q=q,
                                 part="snippet",
                                 order='viewCount',
                                 type='video',
                                 maxResults=max_results,
                                ).execute()


    # ... (既存のコード)
    items_id = []
    items = response['items']
    for item in items:
        item_id = {}
        item_id['video_id'] = item['id']['videoId']
        item_id['channel_id'] = item['snippet']['channelId']
        items_id.append(item_id)
    df_video = pd.DataFrame(items_id)
    return df_video

def get_results(df_video, threshold=50000):
    if df_video.empty: # df_videoが空の場合の処理を追加
        return pd.DataFrame()

    channel_ids = df_video['channel_id'].unique().tolist()
    if not channel_ids: # channel_idsが空の場合の処理を追加
        return pd.DataFrame(columns=['video_id', 'title', 'view_count', 'subscriber_count', 'channel_id'])


    subscriber_list = youtube.channels().list(
        id=','.join(channel_ids),
        part='statistics',
        fields='items(id,statistics(subscriberCount))'
    ).execute()

    subscribers = []
    for item in subscriber_list['items']:
        subscriber = {}
        # 'statistics' キーが存在し、かつ 'subscriberCount' キーが存在するか確認
        if 'statistics' in item and 'subscriberCount' in item['statistics']:
            subscriber['channel_id'] = item['id']
            subscriber['subscriber_count'] = int(item['statistics']['subscriberCount'])
        else:
            subscriber['channel_id'] = item['id']
            # 登録者数が取得できない場合は0またはNoneを設定するなど検討
            subscriber['subscriber_count'] = 0
        subscribers.append(subscriber)

    df_subscribers = pd.DataFrame(subscribers)

    df = pd.merge(left=df_video, right=df_subscribers, on='channel_id')
    df_extracted = df[df['subscriber_count'] < threshold]

    if df_extracted.empty: # 抽出後のデータがない場合
         return pd.DataFrame(columns=['video_id', 'title', 'view_count', 'subscriber_count', 'channel_id'])

    video_ids = df_extracted['video_id'].tolist()
    videos_list = youtube.videos().list(
                id=','.join(video_ids),
                part='snippet,contentDetails,statistics',
                fields='items(id,snippet(title,publishedAt),contentDetails(duration),statistics(viewCount))'
            ).execute()

    videos_info = []
    items = videos_list['items']
    for item in items:
        video_info = {}
        video_info['video_id'] = item['id']
        video_info['title'] = item['snippet']['title']
        video_info['view_count'] = item['statistics']['viewCount'] # viewCountが必ずあるとは限らない場合、getを使う
        videos_info.append(video_info)

    df_videos_info = pd.DataFrame(videos_info)

    if df_videos_info.empty: # 動画情報が取得できなかった場合
        # df_extractedに必要なカラムだけ残すか、空のDataFrameを返す
        # ここでは、必要なカラムのみを持つ空のDataFrameの可能性も考慮
        if not df_extracted.empty and 'video_id' in df_extracted.columns:
             # 最終的なresultsに必要なカラムだけを持つように調整
            results = df_extracted[['video_id', 'channel_id', 'subscriber_count']].copy()
            results['title'] = None
            results['view_count'] = None
            results = results.loc[:, ['video_id', 'title', 'view_count', 'subscriber_count', 'channel_id']]
            return results
        return pd.DataFrame(columns=['video_id', 'title', 'view_count', 'subscriber_count', 'channel_id'])


    try:
        results = pd.merge(left=df_extracted, right=df_videos_info, on='video_id')
        results = results.loc[:, ['video_id', 'title', 'view_count', 'subscriber_count', 'channel_id']]
    except KeyError as e: # マージやカラム選択でエラーが出た場合
        st.warning(f"結果の整形中にエラーが発生しました: {e}。空の結果を返します。")
        return pd.DataFrame(columns=['video_id', 'title', 'view_count', 'subscriber_count', 'channel_id'])
    except Exception as e:
        st.error(f"予期せぬエラーが発生しました: {e}")
        return pd.DataFrame()


    return results

# --- Streamlit UI部分 ---
st.title('YouTube分析アプリ')

st.sidebar.write("""
## クエリとしきい値の設定""")
st.sidebar.write("""
### クエリの入力""")
query = st.sidebar.text_input('検索クエリを入力してください', 'Excel')

st.sidebar.write("""
### 閾値の設定""")
threshold = st.sidebar.slider("登録者数の閾値", 100, 100000, 10000)

st.markdown('### 選択中のパラメータ')
st.markdown(f"""
- 検索クエリ: {query}
- 登録者数の閾値: {threshold}
""")

# youtubeオブジェクトが正しく初期化されていれば、ここでエラーは起きない
if 'youtube' in locals(): # youtubeオブジェクトが存在するか確認
    df_video = video_search(youtube, q=query, max_results=50)
    if not df_video.empty:
        results = get_results(df_video, threshold=threshold)
        st.write("### 分析結果", results)
    else:
        st.write("### 分析結果")
        st.info("検索結果に該当する動画が見つかりませんでした。")
        results = pd.DataFrame() # resultsを空のDataFrameとして定義
else:
    st.error("YouTube APIクライアントが初期化されていません。")
    results = pd.DataFrame() # resultsを空のDataFrameとして定義

st.write("### 動画再生")

video_id_input = st.text_input('動画IDを入力してください') # 変数名を変更 (video_idとの衝突を避ける)
# 正しいYouTube動画URL形式を使用
# 例: https://www.youtube.com/watch?v={VIDEO_ID}
# st.video はこの形式のURLを直接サポートしています。
# url = f"https://youtu.be/{video_id_input}" # この形式は正しくない可能性が高い

video_field = st.empty()
video_field.write('こちらに動画が表示されます')

if st.button('ビデオ表示'):
    if len(video_id_input) > 0:
        try:
            # st.video に直接YouTubeの動画URLを渡す
            video_url = f"https://www.youtube.com/watch?v={video_id_input}"
            video_field.video(video_url)
        except Exception as e: # より具体的なエラーを補足した方が良い場合もある
            st.error(
                f"""
                **おっと！何かエラーが起きているようです。** :(
                エラー内容: {e}
                """
            )
    else:
        st.warning("動画IDを入力してください。")


