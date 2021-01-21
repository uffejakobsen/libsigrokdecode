##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2014 Torsten Duwe <duwe@suse.de>
## Copyright (C) 2014 Sebastien Bourdelin <sebastien.bourdelin@savoirfairelinux.com>
## Copyright (C) 2018 Uffe Jakobsen <uffe@uffe.org>
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, see <http://www.gnu.org/licenses/>.
##


import sigrokdecode as srd
from collections import deque


class SamplerateError(Exception):
    pass


#
#
#
def normalize_time(t):
    fmt_time = "%.0f "
    if abs(t) >= 1.0:
        return (fmt_time + "s") % (t)
    elif abs(t) >= 0.001:
        return (fmt_time + "ms") % (t * 1000.0)
    elif abs(t) >= 0.000001:
        return (fmt_time + "μs") % (t * 1000.0 * 1000.0)
    elif abs(t) >= 0.000000001:
        return (fmt_time + "ns") % (t * 1000.0 * 1000.0 * 1000.0)
    elif abs(t) == 0.0:
        return (fmt_time % (t))
    return ("%f" % (t))


#
#
#
def normalize_freq(t):
    fmt_freq = "%.3f "
    if abs(t) >= 1.0:
        return (fmt_freq + "Hz") % ((1/t))
    elif abs(t) >= 0.001:
        if 1/t/1000 < 1:
            return (fmt_freq + "Hz") % ((1/t))
        else:
            return (fmt_freq + "kHz") % ((1/t)/1000)
    elif abs(t) >= 0.000001:
        if 1/t/1000/1000 < 1:
            return (fmt_freq + "kHz") % ((1/t)/1000)
        else:
            return (fmt_freq + "MHz") % ((1/t)/1000/1000)
    elif abs(t) >= 0.000000001:
        if 1/t/1000/1000/1000:
            return (fmt_freq + "MHz") % ((1/t)/1000/1000)
        else:
            return (fmt_freq + "GHz") % ((1/t)/1000/1000/1000)
    elif abs(t) == 0.0:
        return (fmt_freq % (t))
    return ("%f" % (t))


#
#
#
def normalize_time_freq(t):
    fmt_time = "%.3f "
    fmt_freq = "%.3f "
    if abs(t) >= 1.0:
        return (fmt_time + 's  (' + fmt_freq + 'Hz)') % (t, (1/t))
    elif abs(t) >= 0.001:
        if 1/t/1000 < 1:
            return (fmt_time + 'ms (' + fmt_freq + 'Hz)') % (t * 1000.0, (1/t))
        else:
            return (fmt_time + 'ms (' + fmt_freq + 'kHz)') % (t * 1000.0, (1/t)/1000)
    elif abs(t) >= 0.000001:
        if 1/t/1000/1000 < 1:
            return (fmt_time + 'μs (' + fmt_freq + 'kHz)') % (t * 1000.0 * 1000.0, (1/t)/1000)
        else:
            return (fmt_time + 'μs (' + fmt_freq + 'MHz)') % (t * 1000.0 * 1000.0, (1/t)/1000/1000)
    elif abs(t) >= 0.000000001:
        if 1/t/1000/1000/1000:
            return (fmt_time + 'ns (' + fmt_freq + 'MHz)') % (t * 1000.0 * 1000.0 * 1000.0, (1/t)/1000/1000)
        else:
            return (fmt_time + 'ns (' + fmt_freq + 'GHz)') % (t * 1000.0 * 1000.0 * 1000.0, (1/t)/1000/1000/1000)
    return ('%f' % t)


#
#
#
def terse_times(t, fmt):
    # Strictly speaking these variants are not used in the current
    # implementation, but can reduce diffs during future maintenance.
    if fmt == 'full':
        return [normalize_time(t)]
    # End of "forward compatibility".

    if fmt == 'samples':
        # See below. No unit text, on purpose.
        return ['{:d}'.format(t)]

    # Use caller specified scale, or automatically find one.
    scale, unit = None, None
    if fmt == 'terse-auto':
        if abs(t) >= 1e0:
            scale, unit = 1e0, 's'
        elif abs(t) >= 1e-3:
            scale, unit = 1e3, 'ms'
        elif abs(t) >= 1e-6:
            scale, unit = 1e6, 'us'
        elif abs(t) >= 1e-9:
            scale, unit = 1e9, 'ns'
        elif abs(t) >= 1e-12:
            scale, unit = 1e12, 'ps'
    # Beware! Uses unit-less text when the user picked the scale. For
    # more consistent output with less clutter, thus faster navigation
    # by humans. Can also un-hide text at higher distance zoom levels.
    elif fmt == 'terse-s':
        scale, unit = 1e0, ''
    elif fmt == 'terse-ms':
        scale, unit = 1e3, ''
    elif fmt == 'terse-us':
        scale, unit = 1e6, ''
    elif fmt == 'terse-ns':
        scale, unit = 1e9, ''
    elif fmt == 'terse-ps':
        scale, unit = 1e12, ''
    if scale:
        t *= scale
        return ['{:.0f}{}'.format(t, unit), '{:.0f}'.format(t)]

    # Unspecified format, and nothing auto-detected.
    return ['{:f}'.format(t)]

class Pin:
    (DATA,) = range(1)

class Ann:
    (TIME, TERSE, AVG, AVG2, DELTA, DELTA2, SAMPLES2, TIME2, FREQ2) = range(8)

#
#
#
class Decoder(srd.Decoder):
    api_version = 3
    id = 'timing'
    name = 'Timing'
    longname = 'Timing calculation with frequency and averaging'
    desc = 'Calculate time between edges.'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = []
    tags = ['Clock/timing', 'Util']
    channels = (
        {'id': 'data', 'name': 'Data', 'desc': 'Data line'},
    )
    annotations = (
        ('samples', 'Samples'),
        ('time', 'Time'),
        ('terse', 'Terse'),
        ('average', 'Average'),
        ('freq', 'Freq'),
        ('delta', 'Delta'),
    )
    annotation_rows = (
        ('times', 'Times', (Ann.TIME, Ann.TERSE,)),
        ('averages', 'Averages', (Ann.AVG,)),
        ('deltas', 'Deltas', (Ann.DELTA,)),
        #####
        ('samples', 'Samples', (Ann.SAMPLES2,)),
        ('time', 'Time', (Ann.TIME2,)),
        ('freq', 'Freq', (Ann.FREQ2,)),
        ('delta', 'Delta', (Ann.DELTA2,)),
        ('average', 'Average', (Ann.AVG2,)),
    )

    options = (
        { 'id': 'avg_period', 'desc': 'Averaging period', 'default': 100 },
        { 'id': 'edge', 'desc': 'Edges to check',
          'default': 'any', 'values': ('any', 'rising', 'falling') },
        { 'id': 'delta', 'desc': 'Show delta from last',
          'default': 'no', 'values': ('yes', 'no') },
        { 'id': 'format', 'desc': 'Format of \'time\' annotation',
          'default': 'full', 'values': ('full', 'terse-auto',
          'terse-s', 'terse-ms', 'terse-us', 'terse-ns', 'terse-ps',
          'samples') },
        #####
        {'id': 'edge', 'desc': 'Edges to check', 'default': 'any', 'values': ('any', 'rising', 'falling')},
        {'id': 'show_samples', 'desc': 'Show sample count', 'default': 'yes', 'values': ('yes', 'no')},
        {'id': 'show_timing', 'desc': 'Show timing', 'default': 'yes', 'values': ('yes', 'no')},
        {'id': 'show_freq', 'desc': 'Show frequency', 'default': 'yes', 'values': ('yes', 'no')},
        {'id': 'show_delta', 'desc': 'Show delta from last', 'default': 'yes', 'values': ('yes', 'no')},
        {'id': 'show_avg', 'desc': 'Show Averaging period', 'default': 'yes', 'values': ('yes', 'no')},
        {'id': 'avg_period', 'desc': 'Averaging period', 'default': 100},
    )

    def __init__(self):
        self.reset()
        return

    def reset(self):
        self.samplerate = None
        self.last_samplenum = None
        self.last_n = deque()
        self.chunks = 0
        self.level_changed = False
        self.last_t = None
        return


    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value
        return

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.edge = self.options['edge']
        return

    def decode(self):
        if not self.samplerate:
            raise SamplerateError('Cannot decode without samplerate.')
        edge = self.options['edge']
        avg_period = self.options['avg_period']
        delta = self.options['delta'] == 'yes'
        fmt = self.options['format']
        ss = None
        last_n = deque()
        last_t = None
        while True:
            if edge == 'rising':
                pin = self.wait({Pin.DATA: 'r'})
            elif edge == 'falling':
                pin = self.wait({Pin.DATA: 'f'})
            else:
                pin = self.wait({Pin.DATA: 'e'})

            if not ss:
                ss = self.samplenum
                continue
####<<<<<<< HEAD
            es = self.samplenum
            sa = es - ss
            t = sa / self.samplerate

            if fmt == 'full':
                cls, txt = Ann.TIME, [normalize_time(t)]
            elif fmt == 'samples':
                cls, txt = Ann.TERSE, terse_times(sa, fmt)
            else:
                cls, txt = Ann.TERSE, terse_times(t, fmt)
            if txt:
                self.put(ss, es, self.out_ann, [cls, txt])

            if avg_period > 0:
                if t > 0:
                    last_n.append(t)
                if len(last_n) > avg_period:
                    last_n.popleft()
                average = sum(last_n) / len(last_n)
                cls, txt = Ann.AVG, normalize_time(average)
                self.put(ss, es, self.out_ann, [cls, [txt]])
            if last_t and delta:
                cls, txt = Ann.DELTA, normalize_time(t - last_t)
                self.put(ss, es, self.out_ann, [cls, [txt]])

#####=======
            samples = self.samplenum - self.last_samplenum
            t = samples / self.samplerate

            if t > 0:
                self.last_n.append(t)
            if len(self.last_n) > self.options['avg_period']:
                self.last_n.popleft()

            if self.last_t and self.options['show_samples'] == 'yes':
                self.put(self.last_samplenum, self.samplenum, self.out_ann,
                         [Ann.SAMPLES2, ["%d" % (samples)]])

            if self.options['show_timing'] == 'yes':
                self.put(self.last_samplenum, self.samplenum, self.out_ann,
                         [Ann.TIME2, [normalize_time(t)]])

            if self.options['show_freq'] == 'yes':
                self.put(self.last_samplenum, self.samplenum, self.out_ann,
                         [Ann.FREQ2, [normalize_freq(t)]])

            if self.last_t and self.options['show_delta'] == 'yes':
                self.put(self.last_samplenum, self.samplenum, self.out_ann,
                         [Ann.DELTA2, [normalize_time(t - self.last_t), normalize_time_freq(t - self.last_t)]])

            if self.options['avg_period'] > 0 and self.options['show_avg'] == 'yes':
                self.put(self.last_samplenum, self.samplenum, self.out_ann,
                         [Ann.AVG2, [normalize_time(sum(self.last_n) / len(self.last_n))]])

            self.last_t = t
            self.last_samplenum = self.samplenum
#>>>>>>
            last_t = t
            ss = es

        return
#
# EOF
#
