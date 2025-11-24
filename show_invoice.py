#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freee請求書API - 請求書確認スクリプト（修正版）
エンドポイントを /api/1/invoices に修正
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

# トークンファイルのパス
TOKEN_FILE = 'freee_tokens.json'

class FreeeInvoiceAPI:
    """freee請求書API クライアント"""
    
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
        """トークンの有効性を確認"""
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
                
                print("\n💡 請求書が登録されている事業所を選択してください")
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
    
    def _api_request(self, method, endpoint, **kwargs):
        """APIリクエストを実行"""
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
            del kwargs['headers']
        
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
        """事業所情報を取得"""
        print("\n🏢 事業所情報を取得中...")
        response = self._api_request('GET', '/api/1/companies')
        
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
    
    def get_invoices(self, limit=100, start_date=None, end_date=None, invoice_status=None):
        """請求書一覧を取得（修正版）"""
        if not self.company_id:
            print("❌ company_idが設定されていません")
            return []
        
        print(f"\n📄 請求書一覧を取得中...")
        print(f"   Company ID: {self.company_id}")
        print(f"   取得件数: {limit}")
        if start_date:
            print(f"   開始日: {start_date}")
        if end_date:
            print(f"   終了日: {end_date}")
        if invoice_status:
            print(f"   ステータス: {invoice_status}")
        
        params = {
            'company_id': self.company_id,
            'limit': limit
        }
        
        if start_date:
            params['start_issue_date'] = start_date
        if end_date:
            params['end_issue_date'] = end_date
        if invoice_status:
            params['invoice_status'] = invoice_status
        
        # /api/1/invoices を使用（標準の会計APIエンドポイント）
        response = self._api_request('GET', '/api/1/invoices', params=params)
        
        if response.status_code == 200:
            try:
                # Content-Typeを確認
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type:
                    print(f"⚠️  予期しないContent-Type: {content_type}")
                    print(f"   レスポンス(最初の500文字): {response.text[:500]}")
                    
                    # HTMLエラーページの場合
                    if 'text/html' in content_type:
                        print("\n❌ APIエンドポイントが見つかりません")
                        print("💡 考えられる原因:")
                        print("   1. このアプリに請求書APIへのアクセス権限がない")
                        print("   2. 請求書機能が事業所で有効化されていない")
                        print("   3. 使用しているAPIエンドポイントが正しくない")
                        print("\n📌 確認事項:")
                        print("   - freee会計の「請求書」メニューで請求書を作成できるか確認")
                        print("   - アプリの権限設定で「請求書の参照」権限があるか確認")
                        print("   - https://app.secure.freee.co.jp/developers/applications")
                    return []
                
                data = response.json()
                invoices = data.get('invoices', [])
                print(f"✓ {len(invoices)}件の請求書を取得しました")
                
                if invoices:
                    print("\n取得した請求書:")
                    for i, inv in enumerate(invoices, 1):
                        print(f"   {i}. {inv.get('invoice_number')} - "
                              f"{inv.get('partner_name', 'N/A')} - "
                              f"¥{inv.get('total_amount', 0):,}")
                
                return invoices
            except json.JSONDecodeError as e:
                print(f"❌ JSONデコードエラー: {e}")
                print(f"   レスポンステキスト(最初の1000文字): {response.text[:1000]}")
                return []
        else:
            print(f"❌ 請求書一覧取得に失敗:")
            print(f"   ステータスコード: {response.status_code}")
            print(f"   レスポンス: {response.text[:1000]}")
            
            if response.status_code == 400:
                print("\n💡 考えられる原因:")
                print("   - リクエストパラメータが不正")
                print("   - 指定したcompany_idに対する権限がない")
            elif response.status_code == 403:
                print("\n💡 考えられる原因:")
                print("   - この事業所に請求書機能が有効化されていない")
                print("   - アプリに請求書APIへのアクセス権限がない")
            elif response.status_code == 404:
                print("\n💡 考えられる原因:")
                print("   - APIエンドポイントが正しくない")
                print("   - 請求書APIが利用できないプランの可能性")
            
            return []
    
    def get_invoice_detail(self, invoice_id):
        """請求書の詳細を取得"""
        if not self.company_id:
            print("❌ company_idが設定されていません")
            return None
        
        print(f"\n📋 請求書詳細を取得中... (ID: {invoice_id})")
        
        params = {'company_id': self.company_id}
        response = self._api_request('GET', f'/api/1/invoices/{invoice_id}', params=params)
        
        if response.status_code == 200:
            try:
                invoice = response.json().get('invoice')
                print(f"✓ 請求書詳細を取得しました: {invoice.get('invoice_number')}")
                return invoice
            except json.JSONDecodeError:
                print(f"❌ JSONデコードエラー: {response.text[:500]}")
                return None
        else:
            print(f"❌ 請求書詳細取得に失敗: {response.status_code}")
            print(f"   レスポンス: {response.text[:500]}")
            return None


def get_status_text(status):
    """ステータスを日本語に変換"""
    status_map = {
        'draft': '下書き',
        'unsubmitted': '送付待ち',
        'confirmed': '確定',
        'sent': '送付済み',
        'paid': '入金済み',
        'cancelled': 'キャンセル'
    }
    return status_map.get(status, status)


def format_invoice_summary_table(invoices):
    """請求書一覧をMarkdownテーブル形式に整形"""
    if not invoices:
        return "請求書がありません。"
    
    lines = []
    lines.append("| No | 請求書番号 | 取引先 | 発行日 | 支払期限 | ステータス | 合計金額 |")
    lines.append("|:---:|:---|:---|:---:|:---:|:---:|---:|")
    
    for i, invoice in enumerate(invoices, 1):
        invoice_number = invoice.get('invoice_number', 'N/A')
        partner_name = invoice.get('partner_name', 'N/A')
        issue_date = invoice.get('issue_date', 'N/A')
        payment_date = invoice.get('payment_date', 'N/A')
        status = get_status_text(invoice.get('invoice_status', 'N/A'))
        total_amount = invoice.get('total_amount', 0)
        
        lines.append(f"| {i} | {invoice_number} | {partner_name} | {issue_date} | {payment_date} | {status} | ¥{total_amount:,} |")
    
    return "\n".join(lines)


def format_invoice_detail(invoice):
    """請求書詳細をMarkdown形式に整形"""
    lines = []
    
    lines.append("## 請求書詳細")
    lines.append("")
    
    lines.append("### 基本情報")
    lines.append("")
    lines.append(f"**請求書ID:** {invoice.get('id', 'N/A')}")
    lines.append(f"**請求書番号:** {invoice.get('invoice_number', 'N/A')}")
    lines.append(f"**ステータス:** {get_status_text(invoice.get('invoice_status', 'N/A'))}")
    lines.append(f"**発行日:** {invoice.get('issue_date', 'N/A')}")
    lines.append(f"**支払期限:** {invoice.get('payment_date', 'N/A')}")
    lines.append(f"**件名:** {invoice.get('title', 'N/A')}")
    lines.append("")
    
    lines.append("### 取引先情報")
    lines.append("")
    lines.append(f"**取引先名:** {invoice.get('partner_name', 'N/A')}")
    lines.append(f"**取引先ID:** {invoice.get('partner_id', 'N/A')}")
    lines.append("")
    
    lines.append("### 金額情報")
    lines.append("")
    lines.append(f"**小計:** ¥{invoice.get('sub_total', 0):,}")
    lines.append(f"**消費税:** ¥{invoice.get('tax', 0):,}")
    lines.append(f"**合計金額:** ¥{invoice.get('total_amount', 0):,}")
    lines.append("")
    
    invoice_contents = invoice.get('invoice_contents', [])
    if invoice_contents:
        lines.append("### 請求明細")
        lines.append("")
        lines.append("| No | 項目 | 数量 | 単価 | 税区分 | 金額 |")
        lines.append("|:---:|:---|---:|---:|:---:|---:|")
        
        for i, content in enumerate(invoice_contents, 1):
            description = content.get('description', 'N/A')
            qty = content.get('qty', 0)
            unit_price = content.get('unit_price', 0)
            amount = content.get('amount', 0)
            
            tax_type_map = {
                'tax_included': '内税',
                'tax_excluded': '外税',
                'non_taxable': '非課税',
                'tax_exemption': '免税'
            }
            tax_type_text = tax_type_map.get(content.get('tax_entry_method'), 'N/A')
            
            lines.append(f"| {i} | {description} | {qty} | ¥{unit_price:,} | {tax_type_text} | ¥{amount:,} |")
        
        lines.append("")
    
    if invoice.get('notes'):
        lines.append("### 備考")
        lines.append("")
        lines.append(invoice.get('notes'))
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def format_statistics(invoices):
    """請求書の統計情報をMarkdown形式に整形"""
    lines = []
    
    lines.append("### 統計情報")
    lines.append("")
    
    if not invoices:
        lines.append("請求書がありません。")
        return "\n".join(lines)
    
    status_count = {}
    status_amount = {}
    
    for invoice in invoices:
        status = get_status_text(invoice.get('invoice_status', 'N/A'))
        amount = invoice.get('total_amount', 0)
        
        status_count[status] = status_count.get(status, 0) + 1
        status_amount[status] = status_amount.get(status, 0) + amount
    
    lines.append("**総請求書数:** {}件".format(len(invoices)))
    lines.append("")
    
    lines.append("#### ステータス別集計")
    lines.append("")
    lines.append("| ステータス | 件数 | 合計金額 |")
    lines.append("|:---|---:|---:|")
    
    for status in sorted(status_count.keys()):
        count = status_count[status]
        amount = status_amount[status]
        lines.append(f"| {status} | {count}件 | ¥{amount:,} |")
    
    lines.append("")
    
    total_amount = sum(invoice.get('total_amount', 0) for invoice in invoices)
    lines.append(f"**総合計金額:** ¥{total_amount:,}")
    lines.append("")
    
    return "\n".join(lines)


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='freee請求書確認スクリプト（修正版）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python show_invoice.py              # 通常実行
  python show_invoice.py --reauth     # 再認証して実行
  python show_invoice.py -r           # 再認証して実行（短縮形）
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
    print("freee請求書確認スクリプト（修正版）")
    print("="*60)
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"出力ファイル: {output_file}")
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
        print("\n💡 ヒント: 次回から --reauth オプションで自動的に再認証できます")
        print("   例: python show_invoice.py --reauth")
        
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
        api = FreeeInvoiceAPI()
        
        companies = api.get_company_info()
        
        if not companies:
            print("\n❌ 事業所情報が取得できませんでした")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("# 請求書確認結果\n\n")
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
        print("1. すべての請求書を表示")
        print("2. ステータスで絞り込んで表示")
        print("3. 期間で絞り込んで表示")
        print("4. 最近の請求書を表示（10件）")
        print("="*60)
        
        choice = input("\n選択してください (1-4): ").strip()
        
        invoices = []
        filter_info = ""
        
        if choice == '1':
            invoices = api.get_invoices(limit=100)
            filter_info = "すべての請求書"
            
        elif choice == '2':
            print("\nステータスを選択してください:")
            print("1. 下書き (draft)")
            print("2. 送付待ち (unsubmitted)")
            print("3. 確定 (confirmed)")
            print("4. 送付済み (sent)")
            print("5. 入金済み (paid)")
            print("6. キャンセル (cancelled)")
            
            status_choice = input("\n選択してください (1-6): ").strip()
            status_map = {
                '1': 'draft',
                '2': 'unsubmitted',
                '3': 'confirmed',
                '4': 'sent',
                '5': 'paid',
                '6': 'cancelled'
            }
            
            status = status_map.get(status_choice)
            if status:
                invoices = api.get_invoices(limit=100, invoice_status=status)
                filter_info = f"ステータス: {get_status_text(status)}"
            else:
                print("❌ 無効な選択です")
                return
                
        elif choice == '3':
            print("\n期間を指定してください:")
            start_date = input("開始日 (YYYY-MM-DD): ").strip()
            end_date = input("終了日 (YYYY-MM-DD): ").strip()
            
            if start_date and end_date:
                invoices = api.get_invoices(limit=100, start_date=start_date, end_date=end_date)
                filter_info = f"期間: {start_date} ～ {end_date}"
            else:
                print("❌ 日付が正しく入力されていません")
                return
                
        elif choice == '4':
            invoices = api.get_invoices(limit=10)
            filter_info = "最近の請求書（10件）"
            
        else:
            print("❌ 無効な選択です")
            return
        
        print(f"\n" + "="*60)
        print(f"取得結果: {len(invoices)}件の請求書")
        print("="*60)
        
        show_detail = False
        if invoices and len(invoices) <= 5:
            detail_choice = input("\n詳細情報も表示しますか？ (y/n): ").strip().lower()
            show_detail = (detail_choice == 'y')
        
        print(f"\n📝 結果をファイルに出力中... ({output_file})")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 請求書確認結果\n\n")
            f.write(f"**確認日時:** {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n\n")
            f.write(f"**事業所:** {current_company.get('display_name') if current_company else 'N/A'}\n\n")
            f.write(f"**絞り込み条件:** {filter_info}\n\n")
            f.write("---\n\n")
            
            if invoices:
                f.write(format_statistics(invoices))
                f.write("\n")
                
                f.write("## 請求書一覧\n\n")
                f.write(format_invoice_summary_table(invoices))
                f.write("\n\n")
                
                if show_detail:
                    f.write("## 詳細情報\n\n")
                    for i, invoice in enumerate(invoices, 1):
                        f.write(f"### {i}. {invoice.get('invoice_number', 'N/A')}\n\n")
                        
                        invoice_id = invoice.get('id')
                        if invoice_id:
                            detail = api.get_invoice_detail(invoice_id)
                            if detail:
                                f.write(format_invoice_detail(detail))
                        
                        if i < len(invoices):
                            f.write("\n")
                
                print("\n✅ 請求書の確認が完了しました！")
            else:
                f.write("## 結果\n\n")
                f.write("指定された条件に一致する請求書はありませんでした。\n\n")
                f.write("### 考えられる原因\n\n")
                f.write("1. freee会計に請求書が登録されていない\n")
                f.write("2. freee会計APIの請求書エンドポイントへのアクセス権限がない\n")
                f.write("3. 使用しているAPIエンドポイントがこのプランで利用できない\n\n")
                f.write("**確認方法:**\n")
                f.write("- freee会計: https://secure.freee.co.jp/\n")
                f.write("- 左メニューの「請求書」から請求書を確認できるか試してください\n")
                f.write("- アプリ設定: https://app.secure.freee.co.jp/developers/applications\n")
                print("\n⚠️  該当する請求書が見つかりませんでした")
        
        print(f"\n✅ 結果を {output_file} に出力しました")
        print("\n" + "="*60)
        print("処理完了")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 請求書確認結果\n\n")
            f.write("## ❌ エラーが発生しました\n\n")
            f.write(f"```\n{str(e)}\n```\n\n")
            f.write("### スタックトレース\n\n")
            f.write(f"```\n{traceback.format_exc()}\n```\n")
        
        print(f"\nエラー内容を {output_file} に出力しました")
        sys.exit(1)


if __name__ == '__main__':
    main()