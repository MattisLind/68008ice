// SPDX-License-Identifier: BSD-3-Clause
// Functional port of the MAC mapping/register behavior in MAME's
// src/mame/luxor/abc1600_mmu.cpp, copyright Curt Coder.
// See LICENSES/BSD-3-Clause-MAME.txt. Bus phase timing remains the PIO HAL's.
#include <string.h>
#include "abc1600_memory.h"
#include "cpu68008.h"
abc1600_memory abc1600_model;

static void cio_reset(abc1600_memory *m) {
    memset(m->cio,0,sizeof m->cio);memset(m->cio_output,0,sizeof m->cio_output);
    m->cio[0]=1;m->cio[8]=m->cio[9]=8;
    m->cio[0x23]=m->cio[0x2b]=255;m->cio[6]=15;m->cio[0x1f]=255;
    m->cio_pointer=0;m->cio_state0=0;
}
void abc1600_memory_init(abc1600_memory *m) {
    memset(m,0,sizeof *m);m->status.version=1;
    memset(m->segment,255,sizeof m->segment);memset(m->page,255,sizeof m->page);
    cio_reset(m);
    m->dart_rr0[0]=m->dart_rr0[1]=0x54;
    m->video.clocks_disabled=1;
}
// The mover is asynchronous. Limit work per bus access so the RP2350 can
// continue acknowledging cycles, including the ROM's AMM/busy polling reads.
static void video_step(abc1600_video *v,uint8_t *ram) {
    ++v->ticks;
    if(!v->busy)return;
    uint8_t *pixels=ram+ABC1600_RAM_BYTES;
    int dx=(v->direction&8) ? 1 : -1,dy=(v->direction&4) ? 1 : -1;
    unsigned width=((dx*v->xsize)&1023)+1,height=((dy*v->ysize)&4095)+1;
    for(unsigned work=0;work<16 && v->busy;++work) {
        unsigned x=(v->xto+dx*v->column)&1023,y=(v->ty+dy*v->row)&4095;
        unsigned word=x>>4,at=(y*128)+(word*2);
        uint16_t before=(pixels[at]<<8)|pixels[at+1],out=before;
        do {
            unsigned sx=(v->xfrom+dx*v->column)&1023;
            if(v->flag&0x20)sx=(v->xfrom&0x3f0)|(sx&15);
            unsigned sy=(v->fy+((v->flag&0x10) ? 0 : dy*v->row))&4095;
            unsigned source=sy*128+(sx>>3);
            bool bit=(pixels[source]&(0x80>>(sx&7)))!=0;
            if(v->flag&0x40)bit=!bit;
            uint16_t maskbit=0x8000>>(x&15);
            out=bit ? out|maskbit : out&~maskbit;
            ++v->column;x=(v->xto+dx*v->column)&1023;
        } while(v->column<width && (x>>4)==word);
        pixels[at]=out>>8;pixels[at+1]=out;
        if(v->column==width) {v->column=0;if(++v->row==height) {
            v->busy=0;
            if(!(v->flag&1))v->xto=(v->xto+v->xsize+1)&1023;
            if(!(v->flag&0x10))v->fy=(v->fy+dy*height)&4095;
            if(v->flag&1)v->ty=(v->ty+dy*height)&4095;
        }}
    }
}
static uint8_t video_status(abc1600_video *v) {
    // One 2 MHz character tick per nominal four-clock 68008 byte cycle.
    // This is a deterministic functional clock, not an instruction timing model.
    unsigned raster=(v->crtc[9]&31)+1,lines=(v->crtc[4]+1)*raster+(v->crtc[5]&31);
    unsigned line=(v->ticks/(v->crtc[0]+1))%lines;
    unsigned start=v->crtc[7]*raster,width=v->crtc[3]>>4;
    if(!width)width=16;
    bool sync=line>=start && line<start+width;
    return (sync ? 0x40 : 0)|(v->busy ? 0x80 : 0);
}
static uint8_t cio_read(abc1600_memory *m,unsigned r) {
    if(r>=sizeof m->cio)return 255;
    if(r>=5 && r<=7)return m->cio[r]|0xf0;
    if(r==15)return 0xff; // PC0/2/3 high, idle RTC and NVRAM data high.
    if(r==13 || r==14) {
        unsigned port=r-13;uint8_t direction=m->cio[port ? 0x2b : 0x23];
        uint8_t pins=port ? 0x60 : 0xff;
        return (m->cio_output[port]&~direction)|(pins&direction);
    }
    return m->cio[r];
}
static void cio_write(abc1600_memory *m,unsigned r,uint8_t v) {
    if(r>=sizeof m->cio)return;
    if(!r && (v&1)) {cio_reset(m);return;}
    if(r>=5 && r<=7)v&=15;
    if(r>=13 && r<=15)m->cio_output[r-13]=v;
    m->cio[r]=v;
}
static int device_access(abc1600_memory *m,uint32_t a,bool write,uint8_t *v) {
    abc1600_video *video=&m->video;
    if((a&0x1fff00)==0x1ff100) {
        if(write) {if(a&1)video->crtc[video->crtc_address&31]=*v;else video->crtc_address=*v&31;}
        else *v=(a&1) ? video->crtc[video->crtc_address&31] : 0;
    } else if(a>=0x1ff800 && a<=0x1ffa04) {
        unsigned port=a&255,block=(a>>8)&15;
        if(!write) {*v=block==8 && port==0 ? video_status(video) : 255;return CPU_BUS_OK;}
        if(block==8 && port<8) {
            uint16_t *r=port<2 ? &video->xsize : port<4 ? &video->ysize : port<6 ? &video->xto : &video->ty;
            unsigned high_mask=port<2 || (port>=4 && port<6) ? 3 : 15;
            if(port&1)*r=(*r&0xff00)|*v;else *r=(*r&255)|((*v&high_mask)<<8);
            if(!port)video->direction=*v&12;
        } else if(block==9) {
            if(port<4) {
                uint16_t *r=port<2 ? &video->xfrom : &video->fy;
                if(port&1)*r=(*r&0xff00)|*v;else *r=(*r&255)|((*v&(port<2 ? 3 : 15))<<8);
                if(port==3) {video->busy=1;video->row=video->column=0;++video->moves;}
            } else if(video->clocks_disabled && (port&15)==5)video->ms[port>>4]=*v;
            else if(video->clocks_disabled && (port&15)==7)video->ds[port>>4]=*v;
        } else if(block==10) {
            if(port<2) {
                uint16_t *r=(video->flag&0x80) ? &video->gmdi : &video->wrm;
                if(port&1)*r=(*r&0xff00)|*v;else *r=(*r&255)|(*v<<8);
            } else if(port==2)video->clocks_disabled=0;
            else if(port==3)video->flag=*v;
            else if(port==4)video->display=1;
        }
    } else if((a&0x1fff00)==0x1ff200) {
        unsigned channel=(a&4) ? 0 : 1;bool control=!(a&2);
        unsigned pointer=m->dart_pointer[channel];
        if(write) {
            ++m->io_writes;
            if(!control) {
                // Functional, drained transmitter. No input character is fabricated.
                if(channel==1) {if(m->keyboard_tx_count<sizeof m->keyboard_tx)m->keyboard_tx[m->keyboard_tx_count]=*v;++m->keyboard_tx_count;}
            } else if(pointer) {m->dart[channel][pointer]=*v;m->dart_pointer[channel]=0;}
            else {
                m->dart[channel][0]=*v;m->dart_pointer[channel]=*v&7;
                if((*v&0x38)==0x18) {memset(m->dart[channel],0,8);m->dart_pointer[channel]=0;m->dart_rr0[channel]=0x54;}
                if((*v&0x38)==0x28)m->dart_rr0[channel]&=~0x40;
            }
        } else {
            ++m->io_reads;
            *v=!control ? 0 : pointer==0 ? m->dart_rr0[channel] : pointer==1 ? 1 : 0;
            if(control && !pointer && channel==1)++m->keyboard_polls;
            if(control)m->dart_pointer[channel]=0;
        }
        return CPU_BUS_OK;
    } else if((a&0x1fff00)==0x1ff600) {
        unsigned channel=(a&4) ? 0 : 1;bool data=(a&2)!=0;
        unsigned pointer=m->scc_pointer[channel];
        if(write) {
            ++m->io_writes;
            if(!data) {
                if(pointer) {m->scc[channel][pointer]=*v;m->scc_pointer[channel]=0;}
                else m->scc_pointer[channel]=(*v&7)|((*v&0x38)==8 ? 8 : 0);
            }
        } else {
            ++m->io_reads;
            *v=data ? 0 : pointer==0 ? 4 : pointer==1 ? 1 : m->scc[channel][pointer];
            if(!data)m->scc_pointer[channel]=0;
        }
    } else if((a&0x1fff00)!=0x1ff700)return CPU_BUS_BERR;
    else {
    unsigned port=(a>>1)&3;
    if(write) {
        ++m->io_writes;
        if(m->cio[0]&1) {cio_write(m,m->cio_pointer,*v&1);m->cio_state0=!(m->cio[0]&1);}
        else if(port<3)cio_write(m,15-port,*v);
        else if(m->cio_state0) {m->cio_pointer=*v;m->cio_state0=0;}
        else {cio_write(m,m->cio_pointer,*v);m->cio_state0=!(m->cio[0]&1);}
    } else {
        ++m->io_reads;
        *v=(m->cio[0]&1) ? 0 : cio_read(m,port<3 ? 15-port : m->cio_pointer);
        if(port==3 && !(m->cio[0]&1))m->cio_state0=1;
    }
    }
    return CPU_BUS_OK;
}
static uint32_t segment_address(abc1600_memory *m,uint32_t address,bool ifc2) {
    uint32_t a19=(address>>19)&1;
    uint32_t task=(!a19 && !ifc2) ? 0 : m->status.task;
    uint32_t sega19=a19 && (ifc2 || (address&0x100));
    return (task<<5)|(sega19<<4)|((address>>15)&15);
}
static int error(abc1600_memory *m,bool io) {
    ++m->status.bus_errors;if(io)++m->status.unsupported_io;return CPU_BUS_BERR;
}
int abc1600_memory_access(abc1600_memory *m,const uint8_t *rom,uint8_t *ram,
                          uint32_t address,uint32_t fc,bool write,uint8_t *value) {
    address&=0xfffff;
    video_step(&m->video,ram);
    m->status.last_address=address;m->status.last_fc=fc;m->status.last_write=write;
    m->status.last_physical=UINT32_MAX;
    if(fc!=1 && fc!=2 && fc!=5 && fc!=6)return error(m,false);
    bool fetch=fc==2 || fc==6;
    bool super=(fc&4)!=0;
    bool ifc2=(m->status.magic || !fetch || write) && !super;
    if(!write && !m->status.boote && address<0x20000) {
        m->status.last_target=0;*value=rom[address&0x3fff];return CPU_BUS_OK;
    }
    if(!ifc2 && (address&0x80000)) {
        m->status.last_target=1;
        // MAC register handlers in MAME decode with TR_READ/TR_WRITE even
        // when a user program fetch (MAGIC=0) routed into the MAC window.
        uint32_t sega=segment_address(m,address,!super);
        uint32_t pga=((m->segment[sega]&63)<<4)|((address>>11)&15);
        switch(address&7) {
        case 0:
            if(write) {m->page[pga]=((*value&0xc3)<<8)|(m->page[pga]&255);++m->status.page_high_writes;}
            else {uint32_t high=m->page[pga]>>8;*value=high|((high&2) ? 0x3c : 0);}
            break;
        case 1:
            if(write) {m->page[pga]=(m->page[pga]&0xff00)|*value;++m->status.page_low_writes;}
            else *value=m->page[pga]&255;
            break;
        case 3:
            if(write) {m->segment[sega]=*value&0x7f;++m->status.segment_writes;}
            else *value=(!m->status.magic<<7)|(m->segment[sega]&0x7f);
            break;
        case 5:
            if(write) {m->status.task=*value&15;m->status.boote=!(*value&64);m->status.magic=!(*value&128);++m->status.task_writes;}
            else *value=0;
            break;
        case 7:
            if(!write) {*value=m->status.reset_button|2|(m->status.partst ? 0 : m->status.cause);++m->status.cause_reads;}
            break;
        default:if(!write)*value=0;break;
        }
        return CPU_BUS_OK;
    }
    m->status.last_target=2;
    uint32_t sega=segment_address(m,address,ifc2);
    uint32_t pga=((m->segment[sega]&63)<<4)|((address>>11)&15);
    uint16_t page=m->page[pga];
    uint32_t physical=((page&1023)<<11)|(address&0x7ff);
    m->status.cause=((address>>13)&31)|4;m->status.last_physical=physical;
    if((page&0x8000) || (write && !(page&0x4000)))return error(m,false);
    if(physical<ABC1600_RAM_BYTES) {
        if(write) {ram[physical]=*value;++m->status.ram_writes;}
        else {*value=ram[physical];++m->status.ram_reads;}
    } else if(physical<0x180000) {
        m->status.last_target=5;
        uint32_t at=physical-0x100000;abc1600_video *v=&m->video;
        if(write) {
            uint16_t *latch=(v->flag&0x80) ? &v->wrm : &v->gmdi;
            uint8_t bits=(at&1) ? v->wrm : v->wrm>>8;
            if(at&1)*latch=(*latch&0xff00)|*value;else *latch=(*latch&255)|(*value<<8);
            bits=(at&1) ? v->wrm : v->wrm>>8;
            uint8_t data=(at&1) ? v->gmdi : v->gmdi>>8;
            ram[physical]=(ram[physical]&~bits)|(data&bits);
        } else *value=ram[physical];
    } else if(physical>=0x1fe000) {
        m->status.last_target=4;
        if(device_access(m,physical,write,value))return error(m,true);
    } else {m->status.last_target=3;if(!write)*value=255;}
    return CPU_BUS_OK;
}
