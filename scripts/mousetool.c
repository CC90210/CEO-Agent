#include <ApplicationServices/ApplicationServices.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void post_move(double x, double y) {
    CGEventRef e = CGEventCreateMouseEvent(NULL, kCGEventMouseMoved, CGPointMake(x, y), 0);
    CGEventPost(kCGHIDEventTap, e); CFRelease(e);
}
static void post_click(double x, double y, CGEventType dt, CGEventType ut, CGMouseButton btn) {
    CGPoint p = CGPointMake(x, y);
    CGEventRef d = CGEventCreateMouseEvent(NULL, dt, p, btn);
    CGEventRef u = CGEventCreateMouseEvent(NULL, ut, p, btn);
    CGEventPost(kCGHIDEventTap, d); usleep(50000);
    CGEventPost(kCGHIDEventTap, u); CFRelease(d); CFRelease(u);
}
static double ease(double t) { return t * t * (3.0 - 2.0 * t); }

int main(int argc, char *argv[]) {
    if (argc < 2) { fprintf(stderr,"usage: mousetool <cmd> [args]\n"); return 1; }
    const char *cmd = argv[1];

    if (!strcmp(cmd,"pos")) {
        CGEventRef e = CGEventCreate(NULL); CGPoint p = CGEventGetLocation(e); CFRelease(e);
        printf("{\"ok\":true,\"output\":\"%d,%d\",\"x\":%d,\"y\":%d}\n",(int)p.x,(int)p.y,(int)p.x,(int)p.y);
        return 0;
    }
    if (!strcmp(cmd,"move") && argc>=4) {
        double x=atof(argv[2]),y=atof(argv[3]); post_move(x,y);
        printf("{\"ok\":true,\"output\":\"moved to %d,%d\"}\n",(int)x,(int)y); return 0;
    }
    if (!strcmp(cmd,"click") && argc>=4) {
        double x=atof(argv[2]),y=atof(argv[3]); post_move(x,y); usleep(30000);
        post_click(x,y,kCGEventLeftMouseDown,kCGEventLeftMouseUp,kCGMouseButtonLeft);
        printf("{\"ok\":true,\"output\":\"clicked at %d,%d\"}\n",(int)x,(int)y); return 0;
    }
    if (!strcmp(cmd,"rclick") && argc>=4) {
        double x=atof(argv[2]),y=atof(argv[3]); post_move(x,y); usleep(30000);
        post_click(x,y,kCGEventRightMouseDown,kCGEventRightMouseUp,kCGMouseButtonRight);
        printf("{\"ok\":true,\"output\":\"right-clicked at %d,%d\"}\n",(int)x,(int)y); return 0;
    }
    if (!strcmp(cmd,"dclick") && argc>=4) {
        double x=atof(argv[2]),y=atof(argv[3]); post_move(x,y); usleep(30000);
        post_click(x,y,kCGEventLeftMouseDown,kCGEventLeftMouseUp,kCGMouseButtonLeft); usleep(80000);
        post_click(x,y,kCGEventLeftMouseDown,kCGEventLeftMouseUp,kCGMouseButtonLeft);
        printf("{\"ok\":true,\"output\":\"double-clicked at %d,%d\"}\n",(int)x,(int)y); return 0;
    }
    if (!strcmp(cmd,"animate") && argc>=5) {
        double tx=atof(argv[2]),ty=atof(argv[3]); int dur_ms=atoi(argv[4]); int steps=40;
        CGEventRef ev=CGEventCreate(NULL); CGPoint cur=CGEventGetLocation(ev); CFRelease(ev);
        double sx=cur.x,sy=cur.y; int step_us=(dur_ms*1000)/steps;
        for(int i=1;i<=steps;i++){
            double t=(double)i/steps,te=ease(t);
            post_move(sx+(tx-sx)*te, sy+(ty-sy)*te); usleep(step_us);
        }
        printf("{\"ok\":true,\"output\":\"animated to %d,%d\"}\n",(int)tx,(int)ty); return 0;
    }
    if (!strcmp(cmd,"drag") && argc>=6) {
        double sx=atof(argv[2]),sy=atof(argv[3]),tx=atof(argv[4]),ty=atof(argv[5]);
        int dur_ms=argc>=7?atoi(argv[6]):500; int steps=40;
        post_move(sx,sy); usleep(30000);
        CGEventRef dn=CGEventCreateMouseEvent(NULL,kCGEventLeftMouseDown,CGPointMake(sx,sy),kCGMouseButtonLeft);
        CGEventPost(kCGHIDEventTap,dn); CFRelease(dn); usleep(60000);
        int step_us=(dur_ms*1000)/steps;
        for(int i=1;i<=steps;i++){
            double t=(double)i/steps,te=ease(t);
            double cx=sx+(tx-sx)*te,cy=sy+(ty-sy)*te;
            CGEventRef dr=CGEventCreateMouseEvent(NULL,kCGEventLeftMouseDragged,CGPointMake(cx,cy),kCGMouseButtonLeft);
            CGEventPost(kCGHIDEventTap,dr); CFRelease(dr); usleep(step_us);
        }
        CGEventRef up=CGEventCreateMouseEvent(NULL,kCGEventLeftMouseUp,CGPointMake(tx,ty),kCGMouseButtonLeft);
        CGEventPost(kCGHIDEventTap,up); CFRelease(up);
        printf("{\"ok\":true,\"output\":\"dragged (%d,%d) to (%d,%d)\"}\n",(int)sx,(int)sy,(int)tx,(int)ty); return 0;
    }
    if (!strcmp(cmd,"scroll") && argc>=4) {
        int delta=(!strcmp(argv[2],"up"))?atoi(argv[3]):-atoi(argv[3]);
        CGEventRef e=CGEventCreateScrollWheelEvent(NULL,kCGScrollEventUnitLine,1,delta);
        CGEventPost(kCGHIDEventTap,e); CFRelease(e);
        printf("{\"ok\":true,\"output\":\"scrolled %s %s\"}\n",argv[2],argv[3]); return 0;
    }
    fprintf(stderr,"{\"ok\":false,\"error\":\"unknown: %s\"}\n",cmd); return 1;
}
