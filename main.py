import subprocess
import time
import os
import json
from datetime import datetime, timedelta
import sys
from supabase import create_client, Client
import uuid
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

class TradingBotController:
    def __init__(self):
        # Supabase konfigürasyonu
        self.supabase_url = os.getenv('SUPABASE_URL', '')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        self.supabase_bucket = os.getenv('SUPABASE_BUCKET', 'margingate')
        
        # Supabase client oluştur (eğer config varsa)
        self.supabase = None
        if self.supabase_url and self.supabase_key:
            try:
                self.supabase = create_client(self.supabase_url, self.supabase_key)
            except Exception as e:
                print(f"⚠️  Supabase bağlantısı kurulamadı: {e}")
        
        self.scripts = [
            {
                'name': 'coins_async.py',
                'description': 'Coin listesi güncelleme',
                'timeout': 60,  # Max 60 saniye
                'required_output': 'coins.json'
            },
            {
                'name': 'primary_test.py',
                'description': 'SMC analizi ve alarm tespiti',
                'timeout': 600,  # Max 10 dakika
                'required_output': ['sonuc.json', 'alarm_4h.json', 'alarm_2h.json']
            },
            {
                'name': 'entry_long_signal.py',
                'description': 'Entry sinyalleri (15m CHOCH)',
                'timeout': 300,  # Max 5 dakika
                'required_output': 'entry_long_signals.json'
            },
            {
                'name': 'entry_short_signal.py',
                'description': 'Short entry sinyalleri (30m/15m Bearish CHOCH)',
                'timeout': 300,  # Max 5 dakika
                'required_output': 'entry_short_signals.json'
            }
        ]
        self.cycle_count = 0
        self.wait_between_cycles = 300  # 5 dakika
        self.python_executable = sys.executable  # Mevcut Python yorumlayıcısını kullan
        
    def check_file_exists(self, filename):
        """Dosya varlığını kontrol et"""
        if isinstance(filename, list):
            return all(os.path.exists(f) for f in filename)
        return os.path.exists(filename)
    
    def get_file_age(self, filename):
        """Dosyanın kaç saniye önce oluşturulduğunu hesapla"""
        if os.path.exists(filename):
            file_time = os.path.getmtime(filename)
            current_time = time.time()
            return int(current_time - file_time)
        return None
    
    def upload_to_supabase(self, file_path, filename=None):
        """JSON dosyalarını Supabase Storage'a yükle"""
        if not self.supabase:
            return False
            
        try:
            # Dosya adını oluştur (timestamp olmadan)
            if not filename:
                filename = os.path.basename(file_path)
            
            # Dosyayı oku
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # Önce mevcut dosyayı silmeye çalış (varsa)
            try:
                self.supabase.storage.from_(self.supabase_bucket).remove([filename])
            except:
                pass  # Dosya yoksa hata vermez
            
            # Supabase Storage'a yükle
            result = self.supabase.storage.from_(self.supabase_bucket).upload(
                filename, 
                file_content.encode('utf-8'),
                file_options={"content-type": "application/json"}
            )
            
            # Response yapısı kontrol et
            if hasattr(result, 'error') and result.error:
                print(f"⚠️  {file_path} Supabase'e yüklenirken hata: {result.error}")
                return False
            else:
                print(f"✅ {file_path} Supabase'e yüklendi: {filename}")
                return True
                
        except Exception as e:
            print(f"⚠️  {file_path} upload hatası: {e}")
            return False
    
    def upload_all_results(self):
        """Tüm sonuç dosyalarını Supabase'e yükle"""
        if not self.supabase:
            print("⚠️  Supabase bağlantısı yok, dosyalar yüklenemedi")
            return
            
        files_to_upload = [
            'sonuc.json',
            'alarm_4h.json', 
            'alarm_2h.json',
            'entry_long_signals.json',
            'entry_short_signals.json',
            'coins.json'
        ]
        
        uploaded_count = 0
        
        for file_path in files_to_upload:
            if os.path.exists(file_path):
                # Aynı isimle kaydet (timestamp yok)
                if self.upload_to_supabase(file_path):
                    uploaded_count += 1
        
        print(f"📤 {uploaded_count}/{len(files_to_upload)} dosya Supabase'e yüklendi")
    
    def run_script(self, script_info):
        """Tek bir scripti çalıştır"""
        script_name = script_info['name']
        description = script_info['description']
        timeout = script_info['timeout']
        
        print(f"\n{'='*60}")
        print(f"🔄 {description} başlatılıyor...")
        print(f"📄 Script: {script_name}")
        print(f"⏱️  Timeout: {timeout} saniye")
        print(f"{'='*60}")
        
        try:
            # Script başlangıç zamanı
            start_time = time.time()
            
            # Scripti çalıştır
            process = subprocess.Popen(
                [self.python_executable, script_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Çıktıyı gerçek zamanlı oku
            while True:
                output = process.stdout.readline()
                if output:
                    print(output.strip())
                    
                # Process bitti mi kontrol et
                if process.poll() is not None:
                    break
                    
                # Timeout kontrolü
                if time.time() - start_time > timeout:
                    process.terminate()
                    print(f"\n⚠️  {script_name} timeout nedeniyle sonlandırıldı!")
                    return False
            
            # Kalan çıktıları al
            remaining_output, errors = process.communicate()
            if remaining_output:
                print(remaining_output.strip())
            
            # Hata kontrolü
            if process.returncode != 0:
                print(f"\n❌ {script_name} hata ile sonlandı!")
                if errors:
                    print(f"Hata: {errors}")
                return False
            
            # Çıktı dosyalarını kontrol et
            if 'required_output' in script_info:
                outputs = script_info['required_output']
                if not self.check_file_exists(outputs):
                    print(f"\n⚠️  {script_name} beklenen çıktıları oluşturmadı!")
                    return False
            
            elapsed_time = time.time() - start_time
            print(f"\n✅ {script_name} başarıyla tamamlandı! (Süre: {elapsed_time:.1f} saniye)")
            return True
            
        except FileNotFoundError:
            print(f"\n❌ {script_name} dosyası bulunamadı!")
            return False
        except Exception as e:
            print(f"\n❌ {script_name} çalıştırılırken hata: {e}")
            return False
    
    def show_summary(self):
        """Döngü sonunda özet göster"""
        print(f"\n{'='*80}")
        print(f"📊 SİNYAL ÖZETİ - Cycle #{self.cycle_count}")
        print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")
        
        # Short Sinyaller
        short_coins = []
        try:
            with open('entry_short_signals.json', 'r') as f:
                data = json.load(f)
                short_coins = data.get('active_signals', [])
        except:
            pass
            
        print(f"🔴 SHORT SİNYALLERİ ({len(short_coins)}):")
        if short_coins:
            for signal in short_coins:
                symbol = signal.get('symbol', 'N/A')
                timeframes = signal.get('above_range_timeframes', [])
                tf_text = '/'.join(timeframes) if timeframes else 'N/A'
                print(f"   • {symbol} (Range üstü: {tf_text})")
        else:
            print("   Aktif short sinyali yok")
        
        # Long Sinyaller - Range İçi
        long_range_coins = []
        try:
            with open('alarm_4h.json', 'r') as f:
                data = json.load(f)
                long_range_coins.extend([
                    {'symbol': alarm['symbol'], 'interval': '4h', 'position': alarm.get('range_position_pct', 0)}
                    for alarm in data.get('alarms', [])
                ])
        except:
            pass
            
        try:
            with open('alarm_2h.json', 'r') as f:
                data = json.load(f)
                long_range_coins.extend([
                    {'symbol': alarm['symbol'], 'interval': '2h', 'position': alarm.get('range_position_pct', 0)}
                    for alarm in data.get('alarms', [])
                ])
        except:
            pass
        
        print(f"\n🟢 LONG SİNYALLERİ - RANGE İÇİ ({len(long_range_coins)}):")
        if long_range_coins:
            # Symbol'a göre grupla
            symbols_dict = {}
            for coin in long_range_coins:
                symbol = coin['symbol']
                if symbol not in symbols_dict:
                    symbols_dict[symbol] = []
                symbols_dict[symbol].append(coin)
            
            for symbol, coins in sorted(symbols_dict.items()):
                timeframes = []
                for coin in coins:
                    pos = coin['position']
                    timeframes.append(f"{coin['interval']}({pos:.1f}%)")
                print(f"   • {symbol} ({', '.join(timeframes)})")
        else:
            print("   Range içi long sinyali yok")
            
        # Long Sinyaller - Entry (CHOCH)
        long_entry_coins = []
        try:
            with open('entry_long_signals.json', 'r') as f:
                data = json.load(f)
                long_entry_coins = data.get('active_signals', [])
        except:
            pass
        
        print(f"\n🟢 LONG SİNYALLERİ - ENTRY (CHOCH) ({len(long_entry_coins)}):")
        if long_entry_coins:
            for signal in long_entry_coins:
                symbol = signal.get('symbol', 'N/A')
                choch_level = signal.get('choch_level', 0)
                current_price = signal.get('current_price', 0)
                print(f"   • {symbol} (CHOCH: ${choch_level:.4f}, Fiyat: ${current_price:.4f})")
        else:
            print("   Entry CHOCH sinyali yok")
            
        # Toplam özet
        total_coins = 0
        try:
            with open('coins.json', 'r') as f:
                coins_data = json.load(f)
                total_coins = len(coins_data.get('symbols', []))
        except:
            pass
        
        print(f"\n📊 TOPLAM: {total_coins} coin tarandı")
        print(f"{'='*80}")
    
    def run_cycle(self):
        """Tek bir döngü çalıştır"""
        self.cycle_count += 1
        print(f"\n{'#'*60}")
        print(f"🔄 DÖNGÜ #{self.cycle_count} BAŞLADI")
        print(f"🕐 Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}")
        
        # Her scripti sırayla çalıştır
        for script_info in self.scripts:
            success = self.run_script(script_info)
            
            if not success:
                print(f"\n⚠️  {script_info['name']} başarısız oldu, döngü devam ediyor...")
                # Hata durumunda da devam et, ancak kısa bir bekleme yap
                time.sleep(5)
                continue
            
            # Scriptler arası kısa bekleme
            time.sleep(2)
        
        # Döngü özeti
        self.show_summary()
        
        # Sonuçları Supabase'e yükle
        self.upload_all_results()
    
    def run_forever(self):
        """Sonsuz döngüde çalıştır"""
        print("🚀 Trading Bot Controller Başlatıldı!")
        print(f"📌 Python: {self.python_executable}")
        print(f"📂 Çalışma dizini: {os.getcwd()}")
        print(f"⏰ Döngüler arası bekleme: {self.wait_between_cycles} saniye")
        
        # Supabase bağlantı durumu
        if self.supabase:
            print(f"✅ Supabase bağlantısı aktif (Bucket: {self.supabase_bucket})")
        else:
            print("⚠️  Supabase bağlantısı yok - sonuçlar sadece lokal kaydedilecek")
        
        try:
            while True:
                # Döngüyü çalıştır
                cycle_start = time.time()
                self.run_cycle()
                cycle_duration = time.time() - cycle_start
                
                # Sonraki döngü için bekle
                print(f"\n⏳ Sonraki döngü için {self.wait_between_cycles} saniye bekleniyor...")
                print(f"📊 Son döngü süresi: {cycle_duration:.1f} saniye")
                print(f"🔄 Sonraki döngü: {datetime.now() + timedelta(seconds=self.wait_between_cycles)}")
                
                # Bekleme süresini göster
                for remaining in range(self.wait_between_cycles, 0, -10):
                    print(f"\r⏱️  Kalan süre: {remaining} saniye", end='', flush=True)
                    time.sleep(min(10, remaining))
                print("\r" + " " * 50 + "\r", end='')  # Satırı temizle
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 Bot durduruldu! (Toplam döngü: {self.cycle_count})")
            print("👋 Güle güle!")
        except Exception as e:
            print(f"\n\n❌ Beklenmeyen hata: {e}")
            print("🔄 Bot yeniden başlatılmalı...")

def main():
    """Ana fonksiyon"""
    controller = TradingBotController()
    
    # Gerekli dosyaları kontrol et
    required_files = ['coins_async.py', 'primary_test.py', 'entry_long_signal.py', 'entry_short_signal.py']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print("❌ Eksik dosyalar var:")
        for f in missing_files:
            print(f"   - {f}")
        print("\nLütfen tüm dosyaların mevcut olduğundan emin olun.")
        return
    
    # Botu başlat
    controller.run_forever()

if __name__ == "__main__":
    main()