#!/usr/bin/env python3
"""
OS Shell Emulator - Вариант №7
Полная реализация всех 5 этапов.
"""

import sys
import os
import shlex
import json
import zipfile
import base64
import yaml
from datetime import datetime
from pathlib import Path

# ============================================
# Класс VFS (Виртуальная файловая система)
# ============================================
class VFS:
    def __init__(self):
        self.root = {"type": "dir", "children": {}}
        self.current_path = "/"
    
    def normalize_path(self, path):
        """Приводит путь к абсолютному виду внутри VFS"""
        if path.startswith("/"):
            target = path
        else:
            target = os.path.join(self.current_path, path).rstrip("/")
        
        # Упрощённая нормализация
        parts = [p for p in target.split("/") if p not in ("", ".")]
        resolved = []
        for p in parts:
            if p == "..":
                if resolved:
                    resolved.pop()
            else:
                resolved.append(p)
        return "/" + "/".join(resolved) if resolved else "/"
    
    def get_node(self, path):
        """Возвращает узел по пути"""
        path = self.normalize_path(path)
        if path == "/":
            return self.root
        
        parts = [p for p in path.split("/") if p]
        node = self.root
        for part in parts:
            if part in node.get("children", {}):
                node = node["children"][part]
            else:
                return None
        return node
    
    def load_from_zip(self, zip_path):
        """Загружает VFS из ZIP-архива"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for info in zf.infolist():
                    path = info.filename.rstrip("/")
                    parts = path.split("/")
                    
                    node = self.root
                    for i, part in enumerate(parts):
                        if i == len(parts) - 1 and not info.is_dir():
                            # Файл
                            content = zf.read(info.filename)
                            node.setdefault("children", {})[part] = {
                                "type": "file",
                                "content": base64.b64encode(content).decode(),
                                "permissions": 0o644
                            }
                        else:
                            # Директория
                            if part not in node.get("children", {}):
                                node.setdefault("children", {})[part] = {
                                    "type": "dir",
                                    "children": {},
                                    "permissions": 0o755
                                }
                            node = node["children"][part]
            return True
        except Exception as e:
            print(f"Ошибка загрузки VFS: {e}")
            return False
    
    def list_dir(self, path="."):
        """Список содержимого директории"""
        target = self.normalize_path(path)
        node = self.get_node(target)
        
        if not node:
            return f"Ошибка: директория '{path}' не найдена"
        if node["type"] != "dir":
            return f"Ошибка: '{path}' не директория"
        
        items = []
        for name, child in node.get("children", {}).items():
            typ = "d" if child["type"] == "dir" else "-"
            perm = oct(child.get("permissions", 0))[-3:]
            items.append(f"{typ}{perm} {name}")
        
        return "\n".join(items) if items else "(пусто)"
    
    def change_dir(self, path):
        """Смена текущей директории"""
        target = self.normalize_path(path)
        node = self.get_node(target)
        
        if not node:
            return f"Ошибка: директория '{path}' не найдена"
        if node["type"] != "dir":
            return f"Ошибка: '{path}' не директория"
        
        self.current_path = target
        return f"Переход в {target}"
    
    def cat_file(self, path):
        """Вывод содержимого файла"""
        target = self.normalize_path(path)
        node = self.get_node(target)
        
        if not node:
            return f"Ошибка: файл '{path}' не найден"
        if node["type"] != "file":
            return f"Ошибка: '{path}' не файл"
        
        content = node.get("content", "")
        try:
            return base64.b64decode(content).decode()
        except:
            return content
    
    def chmod(self, mode, path):
        """Изменение прав доступа"""
        target = self.normalize_path(path)
        node = self.get_node(target)
        
        if not node:
            return f"Ошибка: '{path}' не найден"
        
        try:
            # mode может быть строкой "755" или числом
            if isinstance(mode, str):
                mode = int(mode, 8)
            node["permissions"] = mode
            return f"Правa {oct(mode)} установлены для '{path}'"
        except ValueError:
            return f"Ошибка: неверный формат прав '{mode}'"

# ============================================
# Класс эмулятора (основной)
# ============================================
class ShellEmulator:
    def __init__(self, args):
        self.vfs = VFS()
        self.vfs_name = "default_vfs"
        self.running = True
        self.history = []
        self.config = {
            "vfs_path": args.get("vfs_path"),
            "log_path": args.get("log_path"),
            "startup_script": args.get("startup_script"),
            "config_file": args.get("config_file")
        }
        
        # Загружаем конфиг из YAML если указан
        if self.config["config_file"] and os.path.exists(self.config["config_file"]):
            self.load_yaml_config()
        
        # Отладочный вывод параметров
        print("=== Параметры запуска ===")
        for key, value in self.config.items():
            print(f"{key}: {value}")
        print("=========================")
        
        # Инициализация логгера
        self.logger = Logger(self.config["log_path"])
        
        # Загрузка VFS
        if self.config["vfs_path"]:
            self.load_vfs()
        
        # Выполнение стартового скрипта
        if self.config["startup_script"]:
            self.run_startup_script()
    
    def load_yaml_config(self):
        """Загружает конфиг из YAML файла"""
        try:
            with open(self.config["config_file"], 'r') as f:
                yaml_config = yaml.safe_load(f) or {}
            
            # Приоритет: аргументы командной строки > YAML
            for key in ["vfs_path", "log_path", "startup_script"]:
                if not self.config[key] and key in yaml_config:
                    self.config[key] = yaml_config[key]
        except Exception as e:
            print(f"Ошибка чтения конфига: {e}")
    
    def load_vfs(self):
        """Загружает VFS"""
        vfs_path = self.config["vfs_path"]
        if not os.path.exists(vfs_path):
            print(f"Ошибка: файл VFS '{vfs_path}' не найден")
            return
        
        print(f"Загрузка VFS из {vfs_path}...")
        if vfs_path.endswith(".zip"):
            if self.vfs.load_from_zip(vfs_path):
                print("VFS успешно загружена")
            else:
                print("Ошибка загрузки VFS")
        else:
            print("Ошибка: формат VFS не поддерживается")
    
    def run_startup_script(self):
        """Выполняет стартовый скрипт"""
        script_path = self.config["startup_script"]
        if not os.path.exists(script_path):
            print(f"Ошибка: скрипт '{script_path}' не найден")
            return
        
        print(f"Выполнение стартового скрипта: {script_path}")
        try:
            with open(script_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    print(f"\n[{line_num}] > {line}")
                    output = self.execute_command(line)
                    if output:
                        print(output)
        except Exception as e:
            print(f"Ошибка выполнения скрипта: {e}")
    
    def expand_env_vars(self, text):
        """Раскрывает переменные окружения"""
        if "$HOME" in text:
            text = text.replace("$HOME", os.path.expanduser("~"))
        return text
    
    def parse_input(self, user_input):
        """Парсит ввод пользователя"""
        try:
            return shlex.split(user_input)
        except:
            return user_input.split()
    
    def execute_command(self, user_input):
        """Выполняет одну команду"""
        user_input = self.expand_env_vars(user_input)
        parts = self.parse_input(user_input)
        
        if not parts:
            return ""
        
        cmd = parts[0]
        args = parts[1:]
        
        # Логирование команды
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "command": cmd,
            "args": args,
            "error": None
        }
        
        try:
            if cmd == "exit":
                self.running = False
                result = "Выход из эмулятора"
            elif cmd == "ls":
                path = args[0] if args else "."
                result = self.vfs.list_dir(path)
            elif cmd == "cd":
                path = args[0] if args else "/"
                result = self.vfs.change_dir(path)
            elif cmd == "whoami":
                result = os.getlogin()
            elif cmd == "date":
                result = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif cmd == "cat":
                if not args:
                    result = "Ошибка: укажите файл"
                else:
                    result = self.vfs.cat_file(args[0])
            elif cmd == "chmod":
                if len(args) < 2:
                    result = "Ошибка: chmod MODE FILE"
                else:
                    result = self.vfs.chmod(args[0], args[1])
            else:
                result = f"Ошибка: неизвестная команда '{cmd}'"
                log_entry["error"] = result
        
        except Exception as e:
            result = f"Ошибка выполнения: {e}"
            log_entry["error"] = result
        
        # Сохранение в лог
        self.logger.log(log_entry)
        self.history.append(user_input)
        
        return result
    
    def run_interactive(self):
        """Интерактивный режим REPL"""
        print("\n" + "="*50)
        print("OS Shell Emulator - Вариант №7")
        print("Команды: ls, cd, whoami, date, cat, chmod, exit")
        print("="*50)
        
        while self.running:
            try:
                prompt = f"{self.vfs_name} > "
                user_input = input(prompt).strip()
                
                if not user_input:
                    continue
                
                output = self.execute_command(user_input)
                if output:
                    print(output)
                    
            except KeyboardInterrupt:
                print("\nПрервано пользователем")
                break
            except EOFError:
                print("\nВыход")
                break

# ============================================
# Класс логгера
# ============================================
class Logger:
    def __init__(self, log_path=None):
        self.log_path = log_path
        self.logs = []
    
    def log(self, entry):
        """Добавляет запись в лог"""
        self.logs.append(entry)
        
        if self.log_path:
            try:
                with open(self.log_path, 'a') as f:
                    json.dump(entry, f)
                    f.write("\n")
            except:
                pass  # Игнорируем ошибки записи

# ============================================
# Главная функция
# ============================================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="OS Shell Emulator - Вариант №7")
    parser.add_argument("--vfs-path", help="Путь к VFS (ZIP архив)")
    parser.add_argument("--log-path", help="Путь к лог-файлу")
    parser.add_argument("--startup-script", help="Путь к стартовому скрипту")
    parser.add_argument("--config-file", help="Путь к конфигурационному файлу YAML")
    
    args = parser.parse_args()
    
    # Создаём эмулятор с параметрами
    emulator = ShellEmulator({
        "vfs_path": args.vfs_path,
        "log_path": args.log_path,
        "startup_script": args.startup_script,
        "config_file": args.config_file
    })
    
    # Запускаем интерактивный режим
    emulator.run_interactive()

if __name__ == "__main__":
    main()
