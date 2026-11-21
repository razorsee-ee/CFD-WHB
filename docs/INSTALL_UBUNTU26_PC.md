# Ubuntu 26.04 рядом с Windows на домашнем ПК, без флешки

ПК: i7-9700, 16 ГБ, Windows + blueCFD (остаётся). Способ проверен на ноутбуке 20.11.2026 (Ubuntu 24.04.5):
временный FAT32-раздел с содержимым ISO, загрузчик установщика — на EFI-раздел Windows, разовая загрузка через `bcdedit`.
Уроки ноутбука: прошивка не хотела грузиться с обычного раздела (L:), с EFI-раздела — сразу; BitLocker «зашифрован,
защита выключена» → вариант «рядом с Windows» недоступен, ставили через ручную разметку.

Все команды Windows — в **PowerShell от администратора** (Пуск → PowerShell → правой кнопкой → Run as administrator),
в одном окне, по одной.

## Шаг 0. Проверки (прислать вывод Claude до любых изменений)

```bash
Get-Disk | Format-Table Number,FriendlyName,Size,PartitionStyle
```

```bash
Get-Partition | Format-Table DiskNumber,PartitionNumber,DriveLetter,Size,Type
```

```bash
Get-Volume | Format-Table DriveLetter,FileSystemLabel,FileSystem,Size,SizeRemaining
```

```bash
manage-bde -status C:
```

```bash
Confirm-SecureBootUEFI
```

```bash
Get-CimInstance Win32_BaseBoard | Format-List Manufacturer,Product
```

```bash
Get-CimInstance Win32_VideoController | Format-List Name
```

Что смотрим: диск GPT (UEFI), сколько свободно на C: (или есть ли второй диск), BitLocker, Secure Boot (`True`/`False`;
ошибка «not supported» = загрузка не UEFI, тогда стоп), плата (клавиша Boot Menu), видеокарта (драйверы).

**До шага 1:** бэкап важного; если BitLocker `Protection On` — ключ восстановления (`manage-bde -protectors -get C:`,
48 цифр) записать **не на этот ПК**.

## Шаг 1. Выключить быстрый запуск и гибернацию

```bash
powercfg /h off
```

## Шаг 2. Скачать ISO

https://releases.ubuntu.com/26.04/ → `ubuntu-26.04.1-desktop-amd64.iso` (или более новая точка 26.04.x).
Проверка (необязательно): `Get-FileHash <путь к iso> -Algorithm SHA256`, сравнить с `SHA256SUMS` там же.

## Шаг 3. Разметка (Disk Management)

```bash
diskmgmt.msc
```

1. Правой кнопкой по **C:** → **Shrink Volume** → размер = место под Ubuntu + 10 ГБ
   (Ubuntu минимум 60 ГБ, для расчётов лучше 100–150 ГБ; например `130000` МБ).
2. Правой кнопкой по **Unallocated** → **New Simple Volume** → `10240` МБ → буква **L** → **FAT32**, метка `UBUNTU`.
3. Остальное место оставить **Unallocated** — туда встанет Ubuntu.

Если Disk Management не даёт FAT32 — создать том NTFS, затем:

```bash
Format-Volume -DriveLetter L -FileSystem FAT32 -NewFileSystemLabel UBUNTU
```

## Шаг 4. Содержимое ISO на L:

```bash
$isoPath = "$env:USERPROFILE\Downloads\ubuntu-26.04.1-desktop-amd64.iso"
```

```bash
$iso = Mount-DiskImage -ImagePath $isoPath -PassThru; $d = ($iso | Get-Volume).DriveLetter; $d
```

```bash
robocopy "${d}:\" L:\ /E
```

В итоговой таблице `Failed` = 0 (если что-то не скопировалось — прислать таблицу: у FAT32 предел 4 ГБ на файл).

```bash
Dismount-DiskImage -ImagePath $isoPath
```

## Шаг 5. Загрузчик установщика на EFI-раздел

```bash
mountvol S: /S
```

(если «The directory is not empty» — S: уже занят: `Get-ChildItem S:\ -Force`; если там папка `EFI` — это он, продолжать.)

```bash
New-Item -ItemType Directory -Force S:\EFI\ubuntu-live
```

```bash
Copy-Item L:\EFI\BOOT\*.efi S:\EFI\ubuntu-live\ -Force
```

```bash
Get-ChildItem S:\EFI\ubuntu-live
```

Должны быть `bootx64.efi`, `grubx64.efi`, `mmx64.efi`.

## Шаг 6. Пункт загрузки и разовая загрузка

```bash
$g = (bcdedit /copy '{bootmgr}' /d "Ubuntu installer") -replace '.*(\{[^}]+\}).*','$1'; $g
```

Напечатается GUID в фигурных скобках — записать его (нужен, если окно закроется).

```bash
bcdedit /set $g device partition=S:
```

```bash
bcdedit /set $g path \EFI\ubuntu-live\bootx64.efi
```

```bash
bcdedit /set '{fwbootmgr}' bootsequence $g
```

```bash
mountvol S: /D
```

```bash
shutdown /r /t 0
```

Ожидается чёрное меню GRUB → **Try or Install Ubuntu**. Если снова Windows: при включении клавиша Boot Menu
(ASUS F8, MSI F11, Gigabyte F12, ASRock F11) → **Ubuntu installer**. Если `grub>` или мигает и возвращается — фото Claude.

## Шаг 7. Установка

Language → Accessibility → Keyboard → Internet (кабель/Wi-Fi) → **Install Ubuntu** → **Interactive installation** →
**Default selection** → отметить обе галочки (third-party software, media formats) → **Next**.

**How do you want to install Ubuntu?** — **сфотографировать и прислать до Next.**
- Есть **Install Ubuntu alongside Windows Boot Manager** → он, размер — всё свободное место.
- Пишет про BitLocker / нет «alongside» → **Manual installation**:
  - строка **Free space** → **+** → размер максимум, **Ext4**, точка монтирования **/** → OK;
  - EFI-раздел (VFAT ~100–300 МБ): `/boot/efi`, **Format не ставить**; Windows (NTFS/BitLocker), L: (FAT32), Recovery — не трогать;
  - **Device for boot loader**: весь диск (например `nvme0n1` или `sda`), не раздел;
  - **фото до Next.**

Аккаунт, часовой пояс → **Review**: форматируется только новый ext4-раздел → **Install** (10–20 мин) → **Restart now**.
После перезагрузки — меню GRUB: Ubuntu / Windows Boot Manager.

## Шаг 8. После установки

В Ubuntu (Ctrl+Alt+T):

```bash
sudo apt update && sudo apt -y upgrade
```

```bash
timedatectl set-local-rtc 1
```

(чтобы часы в Windows не съезжали.) OpenFOAM-14 и Claude Desktop — по `docs/LINUX_OF14.md`.

В Windows — убрать временное (PowerShell от администратора):

```bash
bcdedit /delete '{GUID}'
```

```bash
mountvol S: /S
```

```bash
Remove-Item -Recurse -Force S:\EFI\ubuntu-live
```

```bash
mountvol S: /D
```

Диск L: — Disk Management → **Delete Volume**.

## Откат, если что-то пошло не так

| ситуация | что делать |
|---|---|
| установщик не грузится | ничего не сломано: удалить пункт `bcdedit /delete`, папку `ubuntu-live`, том L:, C: → **Extend Volume** |
| после установки сразу грузится Ubuntu без меню | Boot Menu → **Windows Boot Manager**; в Ubuntu `sudo update-grub` |
| Windows: **Automatic Repair** | Troubleshoot → Advanced options → **Startup Repair** (может спросить ключ BitLocker) |
