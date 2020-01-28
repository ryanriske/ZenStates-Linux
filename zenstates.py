#!/usr/bin/env python
import struct
import os
import glob
import argparse
import subprocess

pstates = range(0xC0010064, 0xC001006C)
smucmdaddr = 0x03B10524
smurspaddr = 0x03B10570
smuargaddr = 0x03B10A40


def writesmureg(reg, value=0):
    subprocess.Popen(['setpci', '-v', '-s', '0:0.0',
                      'b8.l={:08X}'.format(reg)], stdout=subprocess.PIPE)
    subprocess.Popen(['setpci', '-v', '-s', '0:0.0',
                      'bc.l={:08X}'.format(value)], stdout=subprocess.PIPE)


def readsmureg(reg):
    subprocess.Popen(['setpci', '-v', '-s', '0:0.0',
                      'b8.l={:08X}'.format(reg)], stdout=subprocess.PIPE)
    p = subprocess.Popen(['setpci', '-v', '-s', '0:0.0',
                          'bc.l'], stdout=subprocess.PIPE)
    print(p.stdout.readline())


def writesmu(cmd, value=0):
    # clear the response register
    writesmureg(smurspaddr, 0)
    # write the value
    writesmureg(smuargaddr, value)
    readsmureg(smuargaddr)
    writesmureg(smuargaddr + 4, 0)
    # send the command
    writesmureg(smucmdaddr, cmd)
    readsmureg(smurspaddr)


def readsmu(cmd):
    writesmureg(smurspaddr, 0)
    writesmureg(smucmdaddr, cmd)
    readsmureg(smuargaddr)


def writemsr(msr, val, cpu=-1):
    try:
        if cpu == -1:
            for c in glob.glob('/dev/cpu/[0-9]*/msr'):
                f = os.open(c, os.O_WRONLY)
                os.lseek(f, msr, os.SEEK_SET)
                os.write(f, struct.pack('Q', val))
                os.close(f)
        else:
            f = os.open('/dev/cpu/%d/msr' % (cpu), os.O_WRONLY)
            os.lseek(f, msr, os.SEEK_SET)
            os.write(f, struct.pack('Q', val))
            os.close(f)
    except:
        raise OSError("msr module not loaded (run modprobe msr)")


def readmsr(msr, cpu=0):
    try:
        f = os.open('/dev/cpu/%d/msr' % cpu, os.O_RDONLY)
        os.lseek(f, msr, os.SEEK_SET)
        val = struct.unpack('Q', os.read(f, 8))[0]
        os.close(f)
        return val
    except:
        raise OSError("msr module not loaded (run modprobe msr)")


def pstate2str(val):
    if val & (1 << 63):
        fid = val & 0xff
        did = (val & 0x3f00) >> 8
        vid = (val & 0x3fc000) >> 14
        ratio = 25*fid/(12.5 * did)
        vcore = 1.55 - 0.00625 * vid
        return "Enabled - FID = %X - DID = %X - VID = %X - Ratio = %.2f - vCore = %.5f" % (fid, did, vid, ratio, vcore)
    else:
        return "Disabled"


def setbits(val, base, length, new):
    return (val ^ (val & ((2 ** length - 1) << base))) + (new << base)


def setfid(val, new):
    return setbits(val, 0, 8, new)


def setdid(val, new):
    return setbits(val, 8, 6, new)


def setvid(val, new):
    return setbits(val, 14, 8, new)


def hex(x):
    return int(x, 16)


parser = argparse.ArgumentParser(description='Sets P-States for Ryzen processors')
parser.add_argument('-l', '--list', action='store_true', help='List all P-States')
parser.add_argument('-p', '--pstate', default=-1, type=int,choices=range(8), help='P-State to set')
parser.add_argument('--enable', action='store_true', help='Enable P-State')
parser.add_argument('--disable', action='store_true', help='Disable P-State')
parser.add_argument('-f', '--fid', default=-1, type=hex, help='FID to set (in hex)')
parser.add_argument('-d', '--did', default=-1, type=hex, help='DID to set (in hex)')
parser.add_argument('-v', '--vid', default=-1, type=hex, help='VID to set (in hex)')
parser.add_argument('--no-gui', action='store_true',help='Run in CLI without GUI')
parser.add_argument('--c6-enable', action='store_true', help='Enable C-State C6')
parser.add_argument('--c6-disable', action='store_true', help='Disable C-State C6')
parser.add_argument('--smu-test-message', action='store_true', help='Send test message to the SMU')
parser.add_argument('--set-oc-frequency', default=550, type=int, help='Send test message to the SMU')
parser.add_argument('--set-oc-vid', default=-1, type=hex, help='Send test message to the SMU')

args = parser.parse_args()

if args.list:
    for p in range(len(pstates)):
        print('P' + str(p) + " - " + pstate2str(readmsr(pstates[p])))
    print('C6 State - Package - ' +
          ('Enabled' if readmsr(0xC0010292) & (1 << 32) else 'Disabled'))
    print('C6 State - Core - ' + ('Enabled' if readmsr(0xC0010296) & ((1 << 22) |
                                                                      (1 << 14) | (1 << 6)) == ((1 << 22) | (1 << 14) | (1 << 6)) else 'Disabled'))

if args.pstate >= 0:
    new = old = readmsr(pstates[args.pstate])
    print('Current P' + str(args.pstate) + ': ' + pstate2str(old))
    if args.enable:
        new = setbits(new, 63, 1, 1)
        print('Enabling state')
    if args.disable:
        new = setbits(new, 63, 1, 0)
        print('Disabling state')
    if args.fid >= 0:
        new = setfid(new, args.fid)
        print('Setting FID to %X' % args.fid)
    if args.did >= 0:
        new = setdid(new, args.did)
        print('Setting DID to %X' % args.did)
    if args.vid >= 0:
        new = setvid(new, args.vid)
        print('Setting VID to %X' % args.vid)
    if new != old:
        if not (readmsr(0xC0010015) & (1 << 21)):
            print('Locking TSC frequency')
            for c in range(len(glob.glob('/dev/cpu/[0-9]*/msr'))):
                writemsr(0xC0010015, readmsr(0xC0010015, c) | (1 << 21), c)
        print('New P' + str(args.pstate) + ': ' + pstate2str(new))
        writemsr(pstates[args.pstate], new)

if args.c6_enable:
    writemsr(0xC0010292, readmsr(0xC0010292) | (1 << 32))
    writemsr(0xC0010296, readmsr(0xC0010296) |
             ((1 << 22) | (1 << 14) | (1 << 6)))
    print('Enabling C6 state')

if args.c6_disable:
    writemsr(0xC0010292, readmsr(0xC0010292) & ~(1 << 32))
    writemsr(0xC0010296, readmsr(0xC0010296) & ~
             ((1 << 22) | (1 << 14) | (1 << 6)))
    print('Disabling C6 state')

if args.smu_test_message:
    writesmu(0x1)
    print('Sending test SMU message')

if args.set_oc_frequency > 550:
    writesmu(0x5c, args.set_oc_frequency)
    print('Set OC frequency to {}MHz'.format(args.set_oc_frequency))

if args.set_oc_vid >= 0:
    writesmu(0x61, args.set_oc_vid)
    print('Set OC VID to %X' % args.set_oc_vid)

if not args.list and args.pstate == -1 and not args.c6_enable and not args.c6_disable and args.no_gui:
    parser.print_help()

# GUI options
if not args.no_gui:
    import PySimpleGUI as sg
    #sg.theme('Dark Teal 9')
    sg.set_options(element_padding=(5, 5), margins=(1, 1), border_width=0)

    # The tab 1, 2, 3 layouts - what goes inside the tab
    tab1_layout = [
        [sg.CBox('OC Mode', default=False, key='ocMode', enable_events=True)],
        [
            sg.Text('All Core Frequency'),
            sg.Spin(
                values=[x for x in range(550, 7000, 25)],
                initial_value=2000,
                enable_events=True,
                disabled=True,
                size=(12, 1),
                key='cpuFrequency')
        ],
        #[sg.Button('Apply', key='applyTab1'), sg.Button('Cancel')]
    ]

    tab2_layout = [
        [sg.CBox(
            'C6-State Package',
            default=readmsr(0xC0010292) & (1 << 32),
            key='c6StatePackage')
         ],
        [sg.CBox(
            'C6-State Core',
            default=readmsr(0xC0010296) & ((1 << 22) | (1 << 14) | (
                1 << 6)) == ((1 << 22) | (1 << 14) | (1 << 6)),
            key='c6StateCore')
         ],
        #[sg.Button('Apply', key='applyTab2'), sg.Button('Cancel')]
    ]
    tab3_layout = [
        [sg.Text('Power Tab')],
        #[sg.Button('Apply', key='applyTab3'), sg.Button('Cancel')]
    ]

    # The TabgGroup layout - it must contain only Tabs
    tab_group_layout = [
        [sg.Tab('CPU', tab1_layout, key='-TAB1-'),
         sg.Tab('P-States', tab2_layout, key='-TAB2-'),
         sg.Tab('Power', tab3_layout, key='-TAB3-')
         ]
    ]

    # The window layout - defines the entire window
    layout = [
        [sg.TabGroup(tab_group_layout,
                     # selected_title_color='blue',
                     # selected_background_color='red',
                     # tab_background_color='green',
                     enable_events=True,
                     # font='Courier 18',
                     key='-TABGROUP-')],
        [sg.Button('Apply', key='applyBtn'), sg.Button('Cancel')]
    ]

    window = sg.Window('ZenStates', layout)

    while True:     # Event Loop
        event, values = window.read()
        if event in (None, 'Cancel'):
            break
        elif event == 'applyBtn' and values['ocMode']:
            writesmu(0x5a)
            writesmu(0x5c, values['cpuFrequency'])
        elif event == 'applyBtn' and not values['ocMode']:
            writesmu(0x5b)
        elif event == 'ocMode':
            window['cpuFrequency'].update(disabled=(not values['ocMode']))
    window.close()
