#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freee請求書API - 見積書確認スクリプト
エンドポイント: https://api.freee.co.jp/iv/quotations（freee請求書専用API）
"""

import os
import sys
import json
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, quote
import requests
from dotenv import load_dotenv
import argparse

# .envファイルを読み込む
load_dotenv()

# 認証情報
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

# API エンドポイント
AUTH_URL = 'https://accounts.secure.freee.co.jp/public_api/authorize'
TOKEN_URL = 'https://accounts.secure.freee.co.jp/public_api/token'
API_BASE_URL = 'https://api.freee.co.jp'

# freee請求書API用のベースパス
INVOICE_API_BASE = '/iv'  # freee請求書API

# トークンファイルのパス（スクリプトと同じディレクトリ）
SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / 'freee_tokens_quotation.json'


class FreeeQuotationAPI:
    """freee見積書API クライアント（freee請求書専用）"""
    
    def __init__(self):
        self.client_id = CLIENT_ID
        self.client_secret = CLIENT_SECRET
        self.access_token = None
        self.refresh_token = None
        self.company_id = None
        self.tokens_loaded = False
        
        if not self.client_id or not self.client_secret:
            raise ValueError("CLIENT_IDとCLIENT_SECRETを.envファイルに設定してください。")
        
        print("\n" + "="*60)
        print("認証プロセス開始")
        print("="*60)
        
        # 既存のトークンを読み込む
        self._load_tokens()
        
        # トークンが無効な場合は再認証
        if not self.tokens_loaded or not self._verify_token():
            print("\n⚠️  トークンが無効です。再認証が必要です。")
            self._authenticate()
        
        # company_idが設定されていない場合のみ取得
        if not self.company_id:
            print("\n📋 company_idを取得しています...")
            self._fetch_company_id()
        else:
            print(f"\n✓ 認証済みの事業所を使用: Company ID {self.company_id}")
        
        print("\n✅ 認証プロセス完了")
        print(f"   Company ID: {self.company_id}")
        print("="*60 + "\n")
    
    def _load_tokens(self):
        """保存されたトークンを読み込む"""
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'r') as f:
                    tokens = json.load(f)
                    self.access_token = tokens.get('access_token')
                    self.refresh_token = tokens.get('refresh_token')
                    self.company_id = tokens.get('company_id')
                    self.tokens_loaded = True
                    print(f"✓ 保存されたトークンを読み込みました ({TOKEN_FILE})")
                    if self.company_id:
                        print(f"  Company ID: {self.company_id}")
            except Exception as e:
                print(f"⚠️  トークンの読み込みに失敗: {e}")
                self.tokens_loaded = False
        else:
            print(f"ℹ️  トークンファイルが見つかりません ({TOKEN_FILE})")
    
    def _save_tokens(self, token_data):
        """トークンをファイルに保存"""
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2)
        print(f"✓ トークンを {TOKEN_FILE} に保存しました")
    
    def _verify_token(self):
        """トークンの有効性を確認（freee会計APIで検証）"""
        if not self.access_token:
            print("⚠️  アクセストークンがありません")
            return False
        
        print("\n🔍 トークンの有効性を確認中...")
        
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        
        try:
            response = requests.get(
                f'{API_BASE_URL}/api/1/companies',
                headers=headers,
                timeout=10
            )
            
            print(f"   レスポンスコード: {response.status_code}")
            
            if response.status_code == 200:
                print("✓ トークンは有効です")
                return True
            elif response.status_code == 401:
                print("⚠️  トークンの有効期限が切れています")
                print("   リフレッシュトークンで更新を試みます...")
                return self._refresh_access_token()
            else:
                print(f"❌ トークン検証エラー: {response.status_code}")
                print(f"   レスポンス: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"❌ トークン検証中にエラー: {e}")
            return False
    
    def _refresh_access_token(self):
        """リフレッシュトークンを使用してアクセストークンを更新"""
        if not self.refresh_token:
            print("❌ リフレッシュトークンがありません")
            return False
        
        print("\n🔄 アクセストークンを更新中...")
        
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token
        }
        
        try:
            response = requests.post(TOKEN_URL, data=data, timeout=10)
            
            print(f"   レスポンスコード: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.refresh_token = token_data['refresh_token']
                
                if self.company_id:
                    token_data['company_id'] = self.company_id
                
                self._save_tokens(token_data)
                print("✓ アクセストークンを更新しました")
                return True
            else:
                print(f"❌ トークン更新失敗: {response.status_code}")
                print(f"   レスポンス: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"❌ トークン更新中にエラー: {e}")
            return False
    
    def _authenticate(self):
        """OAuth認証フローを実行"""
        print("\n" + "="*60)
        print("OAuth認証を開始します")
        print("="*60)
        
        redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
        
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'prompt': 'select_company'
        }
        
        auth_url = f'{AUTH_URL}?{urlencode(params)}'
        
        print("\n以下のURLをブラウザで開いて認証してください:")
        print("-" * 60)
        print(auth_url)
        print("-" * 60)
        
        try:
            webbrowser.open(auth_url)
            print("\n✓ ブラウザを開きました")
        except:
            print("\n⚠️  ブラウザを自動的に開けませんでした")
        
        print("\n認証後、表示される認可コードを入力してください:")
        auth_code = input("認可コード: ").strip()
        
        if not auth_code:
            print("❌ 認可コードが入力されていません")
            sys.exit(1)
        
        print(f"\n🔄 認可コードでトークンを取得中... (コード: {auth_code[:10]}...)")
        
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': auth_code,
            'redirect_uri': redirect_uri
        }
        
        try:
            response = requests.post(TOKEN_URL, data=data, timeout=10)
            
            print(f"   レスポンスコード: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.refresh_token = token_data['refresh_token']
                self.company_id = token_data.get('company_id')
                
                self._save_tokens(token_data)
                print("✓ 認証に成功しました")
                if self.company_id:
                    print(f"  Company ID: {self.company_id}")
            else:
                print(f"❌ 認証失敗: {response.status_code}")
                print(f"   レスポンス: {response.text[:500]}")
                sys.exit(1)
                
        except Exception as e:
            print(f"❌ 認証中にエラー: {e}")
            sys.exit(1)
    
    def _fetch_company_id(self):
        """事業所情報からcompany_idを取得して保存"""
        companies = self.get_company_info()
        if companies and len(companies) > 0:
            if len(companies) > 1:
                print(f"\n📋 {len(companies)}件の事業所が見つかりました:")
                for i, company in enumerate(companies, 1):
                    print(f"   {i}. {company.get('display_name')} (ID: {company.get('id')})")
                
                print("\n💡 見積書が登録されている事業所を選択してください")
                while True:
                    try:
                        choice = input(f"選択してください (1-{len(companies)}): ").strip()
                        idx = int(choice) - 1
                        if 0 <= idx < len(companies):
                            self.company_id = companies[idx].get('id')
                            print(f"\n✓ 選択した事業所: {companies[idx].get('display_name')}")
                            print(f"  Company ID: {self.company_id}")
                            break
                        else:
                            print(f"⚠️  1-{len(companies)}の範囲で入力してください")
                    except ValueError:
                        print("⚠️  数字を入力してください")
            else:
                self.company_id = companies[0].get('id')
                print(f"✓ company_idを取得しました: {self.company_id}")
                print(f"  事業所名: {companies[0].get('display_name')}")
            
            if os.path.exists(TOKEN_FILE):
                try:
                    with open(TOKEN_FILE, 'r') as f:
                        tokens = json.load(f)
                    tokens['company_id'] = self.company_id
                    self._save_tokens(tokens)
                except Exception as e:
                    print(f"⚠️  トークンファイルの更新に失敗: {e}")
        else:
            print("❌ company_idを取得できませんでした")
    
    def _api_request(self, method, endpoint, use_invoice_api=False, **kwargs):
        """APIリクエストを実行"""
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
            del kwargs['headers']
        
        if use_invoice_api:
            url = f'{API_BASE_URL}{INVOICE_API_BASE}{endpoint}'
        else:
            url = f'{API_BASE_URL}{endpoint}'
        
        print(f"\n📡 API リクエスト:")
        print(f"   Method: {method}")
        print(f"   URL: {url}")
        if 'params' in kwargs:
            print(f"   Params: {kwargs['params']}")
        
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=30,
                **kwargs
            )
            
            print(f"   レスポンスコード: {response.status_code}")
            
            if response.status_code == 401:
                print("⚠️  トークンの有効期限が切れました。リフレッシュします...")
                if self._refresh_access_token():
                    headers['Authorization'] = f'Bearer {self.access_token}'
                    response = requests.request(
                        method,
                        url,
                        headers=headers,
                        timeout=30,
                        **kwargs
                    )
                    print(f"   再試行後のレスポンスコード: {response.status_code}")
            
            return response
            
        except Exception as e:
            print(f"❌ APIリクエスト中にエラー: {e}")
            raise
    
    def get_company_info(self):
        """事業所情報を取得（freee会計APIを使用）"""
        print("\n🏢 事業所情報を取得中...")
        response = self._api_request('GET', '/api/1/companies', use_invoice_api=False)
        
        if response.status_code == 200:
            companies = response.json()
            company_list = companies.get('companies', [])
            print(f"✓ {len(company_list)}件の事業所を取得しました")
            for i, company in enumerate(company_list, 1):
                print(f"   {i}. {company.get('display_name')} (ID: {company.get('id')})")
            return company_list
        else:
            print(f"❌ 事業所情報の取得に失敗: {response.status_code}")
            print(f"   レスポンス: {response.text[:500]}")
            return []
    
    def get_quotations(self, limit=100, start_date=None, end_date=None, 
                       sending_status=None):
        """見積書一覧を取得（freee請求書API）
        
        Args:
            limit: 取得件数（最大100）
            start_date: 見積日の開始日（YYYY-MM-DD）
            end_date: 見積日の終了日（YYYY-MM-DD）
            sending_status: 送付ステータス（sent/unsent）
        """
        if not self.company_id:
            print("❌ company_idが設定されていません")
            return []
        
        print(f"\n📄 見積書一覧を取得中（freee請求書API）...")
        print(f"   Company ID: {self.company_id}")
        print(f"   取得件数: {limit}")
        if start_date:
            print(f"   開始日: {start_date}")
        if end_date:
            print(f"   終了日: {end_date}")
        if sending_status:
            print(f"   送付ステータス: {sending_status}")
        
        params = {
            'company_id': self.company_id,
            'limit': min(limit, 100)
        }
        
        if start_date:
            params['start_quotation_date'] = start_date
        if end_date:
            params['end_quotation_date'] = end_date
        if sending_status:
            params['sending_status'] = sending_status
        
        # freee請求書API（/iv/quotations）を使用
        response = self._api_request('GET', '/quotations', params=params, use_invoice_api=True)
        
        if response.status_code == 200:
            try:
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type:
                    print(f"⚠️  予期しないContent-Type: {content_type}")
                    print(f"   レスポンス(最初の500文字): {response.text[:500]}")
                    return []
                
                data = response.json()
                quotations = data.get('quotations', [])
                print(f"✓ {len(quotations)}件の見積書を取得しました")
                
                if quotations:
                    print("\n取得した見積書:")
                    for i, q in enumerate(quotations, 1):
                        partner_name = q.get('partner_name') or q.get('partner_display_name', 'N/A')
                        print(f"   {i}. {q.get('quotation_number')} - "
                              f"{partner_name} - "
                              f"¥{q.get('total_amount', 0):,.0f}")
                
                return quotations
            except json.JSONDecodeError as e:
                print(f"❌ JSONデコードエラー: {e}")
                print(f"   レスポンステキスト(最初の1000文字): {response.text[:1000]}")
                return []
        else:
            print(f"❌ 見積書一覧取得に失敗:")
            print(f"   ステータスコード: {response.status_code}")
            print(f"   レスポンス: {response.text[:1000]}")
            
            if response.status_code == 400:
                print("\n💡 考えられる原因:")
                print("   - リクエストパラメータが不正")
                print("   - 指定したcompany_idに対する権限がない")
            elif response.status_code == 403:
                print("\n💡 考えられる原因:")
                print("   - freee請求書APIへのアクセス権限がない")
                print("   - アプリの権限設定を確認してください")
            elif response.status_code == 404:
                print("\n💡 考えられる原因:")
                print("   - freee請求書サービスが有効化されていない")
            
            return []
    
    def get_quotation_detail(self, quotation_id):
        """見積書の詳細を取得（freee請求書API）"""
        if not self.company_id:
            print("❌ company_idが設定されていません")
            return None
        
        print(f"\n📋 見積書詳細を取得中... (ID: {quotation_id})")
        
        params = {'company_id': self.company_id}
        response = self._api_request('GET', f'/quotations/{quotation_id}', 
                                     params=params, use_invoice_api=True)
        
        if response.status_code == 200:
            try:
                quotation = response.json().get('quotation')
                print(f"✓ 見積書詳細を取得しました: {quotation.get('quotation_number')}")
                return quotation
            except json.JSONDecodeError:
                print(f"❌ JSONデコードエラー: {response.text[:500]}")
                return None
        else:
            print(f"❌ 見積書詳細取得に失敗: {response.status_code}")
            print(f"   レスポンス: {response.text[:500]}")
            return None


def get_sending_status_text(status):
    """送付ステータスを日本語に変換"""
    status_map = {
        'sent': '送付済み',
        'unsent': '送付待ち'
    }
    return status_map.get(status, status or 'N/A')


def get_cancel_status_text(status):
    """取消ステータスを日本語に変換"""
    status_map = {
        'canceled': '取消済み',
        'uncanceled': '有効'
    }
    return status_map.get(status, status or 'N/A')


def format_quotation_summary_table(quotations):
    """見積書一覧をMarkdownテーブル形式に整形"""
    if not quotations:
        return "見積書がありません。"
    
    lines = []
    lines.append("| No | 見積書番号 | 取引先 | 見積日 | 有効期限 | 送付 | 合計金額 |")
    lines.append("|:---:|:---|:---|:---:|:---:|:---:|---:|")
    
    for i, q in enumerate(quotations, 1):
        quotation_number = q.get('quotation_number', 'N/A')
        partner_name = q.get('partner_name') or q.get('partner_display_name', 'N/A')
        quotation_date = q.get('quotation_date', 'N/A')
        expiration_date = q.get('expiration_date') or '-'
        sending_status = get_sending_status_text(q.get('sending_status'))
        total_amount = q.get('total_amount', 0)
        
        lines.append(f"| {i} | {quotation_number} | {partner_name} | {quotation_date} | "
                     f"{expiration_date} | {sending_status} | ¥{total_amount:,.0f} |")
    
    return "\n".join(lines)


def format_quotation_detail(quotation):
    """見積書詳細をMarkdown形式に整形"""
    lines = []
    
    lines.append("## 見積書詳細")
    lines.append("")
    
    lines.append("### 基本情報")
    lines.append("")
    lines.append(f"**見積書ID:** {quotation.get('id', 'N/A')}")
    lines.append(f"**見積書番号:** {quotation.get('quotation_number', 'N/A')}")
    lines.append(f"**送付ステータス:** {get_sending_status_text(quotation.get('sending_status'))}")
    lines.append(f"**取消ステータス:** {get_cancel_status_text(quotation.get('cancel_status'))}")
    lines.append(f"**見積日:** {quotation.get('quotation_date', 'N/A')}")
    lines.append(f"**有効期限:** {quotation.get('expiration_date') or 'N/A'}")
    lines.append(f"**納品期限:** {quotation.get('delivery_deadline') or 'N/A'}")
    lines.append(f"**納品場所:** {quotation.get('delivery_location') or 'N/A'}")
    lines.append(f"**件名:** {quotation.get('subject', 'N/A')}")
    lines.append("")
    
    lines.append("### 取引先情報")
    lines.append("")
    partner_name = quotation.get('partner_name') or quotation.get('partner_display_name', 'N/A')
    lines.append(f"**取引先名:** {partner_name}")
    lines.append(f"**取引先ID:** {quotation.get('partner_id', 'N/A')}")
    if quotation.get('partner_code'):
        lines.append(f"**取引先コード:** {quotation.get('partner_code')}")
    lines.append("")
    
    lines.append("### 金額情報")
    lines.append("")
    lines.append(f"**小計（税別）:** ¥{quotation.get('amount_excluding_tax', 0):,.0f}")
    lines.append(f"**消費税額:** ¥{quotation.get('amount_tax', 0):,.0f}")
    lines.append(f"**税込金額:** ¥{quotation.get('amount_including_tax', 0):,.0f}")
    if quotation.get('amount_withholding_tax'):
        lines.append(f"**源泉所得税:** ¥{quotation.get('amount_withholding_tax', 0):,.0f}")
    lines.append(f"**合計金額:** ¥{quotation.get('total_amount', 0):,.0f}")
    lines.append("")
    
    # 税率別内訳
    if quotation.get('amount_including_tax_10') is not None:
        lines.append("### 税率別内訳")
        lines.append("")
        lines.append("| 税率 | 税抜 | 消費税 | 税込 |")
        lines.append("|:---:|---:|---:|---:|")
        
        amt_ex_10 = quotation.get('amount_excluding_tax_10') or 0
        amt_ex_8 = quotation.get('amount_excluding_tax_8') or 0
        amt_ex_8r = quotation.get('amount_excluding_tax_8_reduced') or 0
        amt_ex_0 = quotation.get('amount_excluding_tax_0') or 0
        
        if amt_ex_10 > 0:
            lines.append(f"| 10% | ¥{amt_ex_10:,.0f} | "
                        f"¥{(quotation.get('amount_tax_10') or 0):,.0f} | "
                        f"¥{(quotation.get('amount_including_tax_10') or 0):,.0f} |")
        if amt_ex_8 > 0:
            lines.append(f"| 8% | ¥{amt_ex_8:,.0f} | "
                        f"¥{(quotation.get('amount_tax_8') or 0):,.0f} | "
                        f"¥{(quotation.get('amount_including_tax_8') or 0):,.0f} |")
        if amt_ex_8r > 0:
            lines.append(f"| 8%（軽減） | ¥{amt_ex_8r:,.0f} | "
                        f"¥{(quotation.get('amount_tax_8_reduced') or 0):,.0f} | "
                        f"¥{(quotation.get('amount_including_tax_8_reduced') or 0):,.0f} |")
        if amt_ex_0 > 0:
            lines.append(f"| 0% | ¥{amt_ex_0:,.0f} | "
                        f"¥{(quotation.get('amount_tax_0') or 0):,.0f} | "
                        f"¥{(quotation.get('amount_including_tax_0') or 0):,.0f} |")
        lines.append("")
    
    # 明細行
    quotation_lines = quotation.get('lines', [])
    if quotation_lines:
        lines.append("### 見積明細")
        lines.append("")
        lines.append("| No | 項目 | 数量 | 単価 | 税率 | 金額（税別） |")
        lines.append("|:---:|:---|---:|---:|:---:|---:|")
        
        for i, line in enumerate(quotation_lines, 1):
            if line.get('type') == 'text':
                lines.append(f"| {i} | {line.get('description', '')} | - | - | - | - |")
            else:
                description = line.get('description', 'N/A')
                qty = line.get('quantity') if line.get('quantity') is not None else 0
                unit_price = line.get('unit_price')
                tax_rate = line.get('tax_rate') if line.get('tax_rate') is not None else 0
                amount = line.get('amount_excluding_tax') if line.get('amount_excluding_tax') is not None else 0
                
                if unit_price is not None:
                    try:
                        unit_price_str = f"¥{float(unit_price):,.0f}"
                    except (ValueError, TypeError):
                        unit_price_str = str(unit_price)
                else:
                    unit_price_str = "-"
                
                tax_rate_str = f"{tax_rate}%" if tax_rate else "0%"
                if line.get('reduced_tax_rate'):
                    tax_rate_str += "（軽減）"
                
                try:
                    amount_str = f"¥{float(amount):,.0f}"
                except (ValueError, TypeError):
                    amount_str = "-"
                
                lines.append(f"| {i} | {description} | {qty} | {unit_price_str} | "
                            f"{tax_rate_str} | {amount_str} |")
        
        lines.append("")
    
    # 備考
    if quotation.get('quotation_note'):
        lines.append("### 備考")
        lines.append("")
        lines.append(quotation.get('quotation_note'))
        lines.append("")
    
    # 社内メモ
    if quotation.get('memo'):
        lines.append("### 社内メモ")
        lines.append("")
        lines.append(quotation.get('memo'))
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def format_statistics(quotations):
    """見積書の統計情報をMarkdown形式に整形"""
    lines = []
    
    lines.append("### 統計情報")
    lines.append("")
    
    if not quotations:
        lines.append("見積書がありません。")
        return "\n".join(lines)
    
    # 送付ステータス別集計
    sending_count = {}
    sending_amount = {}
    
    for q in quotations:
        sending_status = get_sending_status_text(q.get('sending_status'))
        amount = q.get('total_amount', 0)
        
        sending_count[sending_status] = sending_count.get(sending_status, 0) + 1
        sending_amount[sending_status] = sending_amount.get(sending_status, 0) + amount
    
    lines.append(f"**総見積書数:** {len(quotations)}件")
    lines.append("")
    
    lines.append("#### 送付ステータス別集計")
    lines.append("")
    lines.append("| ステータス | 件数 | 合計金額 |")
    lines.append("|:---|---:|---:|")
    
    for status in sorted(sending_count.keys()):
        count = sending_count[status]
        amount = sending_amount[status]
        lines.append(f"| {status} | {count}件 | ¥{amount:,.0f} |")
    
    lines.append("")
    
    total_amount = sum(q.get('total_amount', 0) for q in quotations)
    lines.append(f"**総合計金額:** ¥{total_amount:,.0f}")
    lines.append("")
    
    return "\n".join(lines)


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='freee見積書確認スクリプト（freee請求書API版）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python show_quotation.py              # 通常実行
  python show_quotation.py --reauth     # 再認証して実行
  python show_quotation.py -r           # 再認証して実行（短縮形）
        """
    )
    parser.add_argument(
        '--reauth', '-r',
        action='store_true',
        help='トークンを削除して再認証する'
    )
    
    args = parser.parse_args()
    
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    output_file = script_dir / f"{script_path.stem}.md"
    
    print("\n" + "="*60)
    print("freee見積書確認スクリプト（freee請求書API版）")
    print("="*60)
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"出力ファイル: {output_file}")
    print(f"使用API: freee請求書API（https://api.freee.co.jp/iv）")
    print("="*60)
    
    if args.reauth:
        if os.path.exists(TOKEN_FILE):
            print(f"\n🗑️  再認証オプションが指定されました")
            print(f"    トークンファイルを削除しています...")
            try:
                os.remove(TOKEN_FILE)
                print(f"✓ {TOKEN_FILE} を削除しました")
                print("✓ 新しい認証プロセスを開始します\n")
            except Exception as e:
                print(f"⚠️  トークンファイルの削除に失敗: {e}")
        else:
            print(f"\nℹ️  トークンファイルが存在しません（削除不要）")
    elif os.path.exists(TOKEN_FILE):
        print(f"\n✓ 既存のトークンファイルが見つかりました: {TOKEN_FILE}")
        print("\n以下を選択してください:")
        print("1. 既存のトークンを使用する（通常）")
        print("2. トークンを削除して再認証する（権限追加後の初回実行時）")
        
        choice = input("\n選択してください (1-2, Enter=1): ").strip()
        
        if choice == '2':
            print(f"\n🗑️  トークンファイルを削除しています...")
            try:
                os.remove(TOKEN_FILE)
                print(f"✓ {TOKEN_FILE} を削除しました")
                print("✓ 新しい認証プロセスを開始します")
            except Exception as e:
                print(f"⚠️  トークンファイルの削除に失敗: {e}")
        else:
            print("\n✓ 既存のトークンを使用します")
    else:
        print(f"\nℹ️  トークンファイルが見つかりません")
        print("✓ 新しい認証プロセスを開始します")
    
    try:
        api = FreeeQuotationAPI()
        
        companies = api.get_company_info()
        
        if not companies:
            print("\n❌ 事業所情報が取得できませんでした")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("# 見積書確認結果\n\n")
                f.write("**エラー:** 事業所情報が取得できませんでした。\n")
            return
        
        current_company = None
        for company in companies:
            if company.get('id') == api.company_id:
                current_company = company
                break
        
        if current_company:
            print(f"\n✅ 使用中の事業所: {current_company.get('display_name')} (ID: {api.company_id})")
        else:
            print(f"\n⚠️  事業所が見つかりません (ID: {api.company_id})")
            return
        
        print("\n" + "="*60)
        print("確認メニュー")
        print("="*60)
        print("1. すべての見積書を表示")
        print("2. 送付ステータスで絞り込んで表示")
        print("3. 期間で絞り込んで表示")
        print("4. 最近の見積書を表示（10件）")
        print("="*60)
        
        choice = input("\n選択してください (1-4): ").strip()
        
        quotations = []
        filter_info = ""
        
        if choice == '1':
            quotations = api.get_quotations(limit=100)
            filter_info = "すべての見積書"
            
        elif choice == '2':
            print("\n送付ステータスを選択してください:")
            print("1. 送付待ち (unsent)")
            print("2. 送付済み (sent)")
            
            status_choice = input("\n選択してください (1-2): ").strip()
            status_map = {
                '1': 'unsent',
                '2': 'sent'
            }
            
            status = status_map.get(status_choice)
            if status:
                quotations = api.get_quotations(limit=100, sending_status=status)
                filter_info = f"送付ステータス: {get_sending_status_text(status)}"
            else:
                print("❌ 無効な選択です")
                return
                
        elif choice == '3':
            print("\n期間を指定してください:")
            start_date = input("開始日 (YYYY-MM-DD): ").strip()
            end_date = input("終了日 (YYYY-MM-DD): ").strip()
            
            if start_date and end_date:
                quotations = api.get_quotations(limit=100, start_date=start_date, end_date=end_date)
                filter_info = f"期間: {start_date} ～ {end_date}"
            else:
                print("❌ 日付が正しく入力されていません")
                return
                
        elif choice == '4':
            quotations = api.get_quotations(limit=10)
            filter_info = "最近の見積書（10件）"
            
        else:
            print("❌ 無効な選択です")
            return
        
        print(f"\n" + "="*60)
        print(f"取得結果: {len(quotations)}件の見積書")
        print("="*60)
        
        show_detail = False
        if quotations and len(quotations) <= 5:
            detail_choice = input("\n詳細情報も表示しますか？ (y/n): ").strip().lower()
            show_detail = (detail_choice == 'y')
        
        print(f"\n📝 結果をファイルに出力中... ({output_file})")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 見積書確認結果（freee請求書）\n\n")
            f.write(f"**確認日時:** {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n\n")
            f.write(f"**事業所:** {current_company.get('display_name') if current_company else 'N/A'}\n\n")
            f.write(f"**絞り込み条件:** {filter_info}\n\n")
            f.write(f"**使用API:** freee請求書API\n\n")
            f.write("---\n\n")
            
            if quotations:
                f.write(format_statistics(quotations))
                f.write("\n")
                
                f.write("## 見積書一覧\n\n")
                f.write(format_quotation_summary_table(quotations))
                f.write("\n\n")
                
                if show_detail:
                    f.write("## 詳細情報\n\n")
                    for i, q in enumerate(quotations, 1):
                        f.write(f"### {i}. {q.get('quotation_number', 'N/A')}\n\n")
                        
                        quotation_id = q.get('id')
                        if quotation_id:
                            detail = api.get_quotation_detail(quotation_id)
                            if detail:
                                f.write(format_quotation_detail(detail))
                        
                        if i < len(quotations):
                            f.write("\n")
                
                print("\n✅ 見積書の確認が完了しました！")
            else:
                f.write("## 結果\n\n")
                f.write("指定された条件に一致する見積書はありませんでした。\n\n")
                f.write("### 考えられる原因\n\n")
                f.write("1. freee請求書に見積書が登録されていない\n")
                f.write("2. freee請求書APIへのアクセス権限がない\n")
                f.write("3. freee請求書サービスへの登録が完了していない\n\n")
                f.write("**確認方法:**\n")
                f.write("- freee請求書: https://invoice.freee.co.jp/\n")
                f.write("- freee請求書への登録: https://www.freee.co.jp/invoice/\n")
                print("\n⚠️  該当する見積書が見つかりませんでした")
        
        print(f"\n✅ 結果を {output_file} に出力しました")
        print("\n" + "="*60)
        print("処理完了")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 見積書確認結果\n\n")
            f.write("## ❌ エラーが発生しました\n\n")
            f.write(f"```\n{str(e)}\n```\n\n")
            f.write("### スタックトレース\n\n")
            f.write(f"```\n{traceback.format_exc()}\n```\n")
        
        print(f"\nエラー内容を {output_file} に出力しました")
        sys.exit(1)


if __name__ == '__main__':
    main()