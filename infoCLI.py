import os
import urllib.request
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import unicodedata
from google import genai

# --- Configuration ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("Environment variable 'GOOGLE_API_KEY' is not set.")

# --- AI Analyzer Module ---
class AIAnalyzer:
    """Gemini APIを利用したテキスト解析クラス"""
    
    def __init__(self, api_key: str):
        self.pro_model = 'gemini-3.1-pro-preview'
        self.flash_model = 'gemini-2.5-flash'
        self.client = genai.Client(api_key=api_key)

    def analyze(self, raw_text: str) -> str:
        """
        記事本文を解析する。
        Proモデルで429エラー(Rate Limit)が発生した場合は、Flashモデルへ自動フォールバックする。
        """
        try:
            return self._call_gemini(self.pro_model, raw_text)
        except Exception as e:
            if "429" in str(e):
                print(f"\n[Warning] {self.pro_model} rate limit exceeded. Fallback to {self.flash_model}...")
                try:
                    return self._call_gemini(self.flash_model, raw_text)
                except Exception as e2:
                    return f"[Error] Fallback model failed: {e2}"
            return f"[Error] Analysis failed: {e}"

    def _call_gemini(self, model_name: str, raw_text: str) -> str:
        prompt = f"""
        あなたは情報理工学部の学生として、以下のニュースを分析してください。

        【要件】
        1. 簡潔な文体（体言止め等）を用い、冗長な表現を避けること。
        2. 技術的背景や経済的インパクトを、エンジニアの視点で深掘りすること。
        3. 学生の学習や開発にどう活かせるかの考察を含めること。

        【出力構成】
        ■ 概要
        ■ 技術・経済的要点
        ■ 考察

        記事原文: 
        {raw_text[:5000]}
        """
        response = self.client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

# --- Scraper Module ---
class NewsFetcher:
    """RSSパースおよびWebスクレイピングを行うクラス"""
    
    def fetch_rss_root(self, url: str) -> ET.Element | None:
        try:
            with urllib.request.urlopen(url) as response:
                return ET.fromstring(response.read())
        except Exception as e:
            print(f"[Error] Failed to fetch RSS: {e}")
            return None

    def scrape_article(self, url: str) -> str:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        article_tag = soup.find('article')
        return article_tag.get_text() if article_tag else soup.get_text()

# --- CLI Controller Module ---
class CLIController:
    """CLIのルーティングと表示制御を行うメインコントローラー"""
    
    def __init__(self, api_key: str):
        self.fetcher = NewsFetcher()
        self.analyzer = AIAnalyzer(api_key)
        self.rss_map = {
            '1': ('総合', 'https://news.yahoo.co.jp/rss/topics/top-picks.xml'),
            '2': ('経済', 'https://news.yahoo.co.jp/rss/topics/business.xml'),
            '3': ('IT・科学', 'https://news.yahoo.co.jp/rss/topics/it.xml')
        }

    def run(self):
        while True:
            print("\n" + "="*50)
            print(" InfoCLI v2.0")
            print("="*50)
            for k, v in self.rss_map.items():
                print(f"[{k}] {v[0]}")
            
            cat_choice = input("\nSelect Category (q: quit): ").strip().lower()
            if cat_choice == 'q': 
                break
            if cat_choice not in self.rss_map:
                print("[Error] Invalid selection.")
                continue

            label, url = self.rss_map[cat_choice]
            print(f"\n>> {label} mode loading...")
            root = self.fetcher.fetch_rss_root(url)
            if root is not None:
                self.search_loop(root)

    def search_loop(self, root: ET.Element):
        while True:
            print("\n" + "-"*40)
            keyword_raw = input("Search Keyword [Enter: latest / b: back / q: quit]: ").strip()
            keyword = unicodedata.normalize('NFKC', keyword_raw).lower()

            if keyword == 'q': 
                exit()
            if keyword == 'b': 
                break

            news_list = []
            for item in root.findall('.//item'):
                title = item.find('title').text
                link = item.find('link').text
                if not keyword or keyword in title.lower():
                    news_list.append({'title': title, 'link': link})

            if not news_list:
                print(f"No articles found for '{keyword}'.")
                continue

            print(f"\n--- Article List ({keyword if keyword else 'Latest'}) ---")
            for i, news in enumerate(news_list[:10], 1):
                print(f"[{i}] {news['title']}")

            self.article_select_loop(news_list[:10])

    def article_select_loop(self, news_list: list):
        while True:
            choice = input(f"\nSelect Article (1-{len(news_list)}) / [Enter: back]: ").strip()
            if not choice: 
                break 

            if not choice.isdigit() or not (1 <= int(choice) <= len(news_list)):
                print("[Error] Invalid selection.")
                continue

            target = news_list[int(choice) - 1]
            print(f"\n>> Analyzing: {target['title']} ...")
            
            raw_text = self.fetcher.scrape_article(target['link'])
            report = self.analyzer.analyze(raw_text)
            
            print("\n" + "="*50)
            print(report)
            print("="*50)
            print(f"URL: {target['link']}")
            break

if __name__ == "__main__":
    app = CLIController(GOOGLE_API_KEY)
    app.run()
            
