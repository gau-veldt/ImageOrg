#! /usr/bin/python

"""

        ImageOrg - Image viewer and Organzier
        
        Copyright (C) 2012 Christopher Brian Jack
        (gau_veldt@hotmail.com)
        
        This file is part of ImageOrg.
        
        ImageOrg is free software: you can redistribute it and/or modify
        it under the terms of the GNU General Public License as published by
        the Free Software Foundation, either version 3 of the License, or
        (at your option) any later version.
    
        ImageOrg is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU General Public License for more details.
    
        You should have received a copy of the GNU General Public License
        along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

import os
import os.path
import string
import hashlib
import sqlite3 as dbapi
import Queries

#os.environ['KIVY_IMAGE']='pil'

from math import log

import kivy
kivy.require('1.3.0')

from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.filechooser import FileChooserIconView
from kivy.factory import Factory
from kivy.properties import ListProperty,StringProperty
from kivy.properties import DictProperty,BooleanProperty
from kivy.properties import NumericProperty,ObjectProperty
from kivy.properties import ReferenceListProperty,OptionProperty
from kivy.lang import Builder
from kivy.core.window import Window

def rankColoring(fRank):
    """
    Generate color gradient for rank fraction `fRank`
    
    0.0<=fRank<=1.0

    1.0 is first place
    0.0 is last place
    """
    return (1.0-fRank,fRank,0,1)

colors={
    'tagActive'      : (1,1,.3625,1),
    'tagInactive'    : (.3,.6,.9,1),
    'rankInactive'   : (1,1,1,1),
    'rankGradient'   : rankColoring,
    'resultSelected' : (0,1,1,1),
    'resultNormal'   : (1,1,1,1),
    'sortedColumn'   : (1,1,0,1),
    'normalColumn'   : (1,1,1,1),
    'itemNormal'     : (1,1,1,1),
    'itemDisabled'   : (.5,.5,.5,1),
    'bgNormal'       : (.19,.19,.19,1),
    'bgRank'         : (.25,.25,.25,1),
    'bgHilight'      : (.2,.3,.5,1),
    'bgBrowsing'     : (.2,.3,.4,1)
}

metricPrefixes=['','k','M','G','T','E']

def formatRank(ranking):
    """
    Returns english suffix for place count
    
    @param ranking: place count
    @return: English place count suffix
    """
    ranking=int(ranking)
    tens=int(ranking/10)*10
    ones=int(ranking-tens)
    fmt=['th','st','nd','rd','th','th','th','th','th','th'][ones]
    return fmt

def formatUnit(value,unit,base,gap,prefixes):
    exp=int(log(value,base)/gap)
    mult=base**(exp*gap)
    prefix=prefixes[exp]
    count=int(0.9+(value*100.0/mult))
    count=(count)/100.0
    return "%s %s%s" % (count,prefix,unit)
   
def FormatPixels(pcount):
    return formatUnit(pcount,"P",10,3,metricPrefixes)

def FormatBytes(pcount):
    return formatUnit(pcount,"B",2,10,metricPrefixes)

class FilterTag(Label):
    filterState=OptionProperty('include',options=['include','exclude'])
    
    def __init__(self,*args,**kwargs):
        super(FilterTag,self).__init__(*args,**kwargs)
        self.filterState='exclude'
    
    def on_filterState(self,who,what):
        self.color={
            'include' : [.375,.75,1,1],
            'exclude' : [.187,.375,.5,1]
        }[what]
    
    def on_touch_down(self,touch):
        pos=touch.pos
        if self.collide_point(*pos):
            self.filterState={
                'include' : 'exclude',
                'exclude' : 'include'
            }[self.filterState]

Factory.register('FilterTag',cls=FilterTag)

class TagFilterBox(BoxLayout):
    minWidth=NumericProperty(None)
    minHeight=NumericProperty(None)
    minSize=ReferenceListProperty(minWidth,minHeight)
    tags=ListProperty([])
    
    def on_minSize(self,who,what):
        maxW=0
        for c in self.children:
            w=max(self.minSize[0],8+(c.font_size*len(c.text)))
            maxW=max(maxW,w)
            c.width=w
            c.text_size=(w-8,24)
        self.width=maxW
    
    def on_tags(self,who,what):
        self.clear_widgets()
        h=0
        for tag in self.tags:
            ft=FilterTag(text=tag,height=24,size_hint=(None,None),halign='left')
            self.add_widget(ft)
            h+=24
        self.height=h

Factory.register('TagFilterBox',cls=TagFilterBox)

class ButtonWithDisable(Button):
    activeColor=ListProperty(colors['itemNormal'])
    inactiveColor=ListProperty(colors['itemDisabled'])
    active=BooleanProperty(True)
    def __init__(self,*args,**kwargs):
        super(ButtonWithDisable,self).__init__(*args,**kwargs)
    def on_active(self,who,what):
        if (what):
            self.color=self.activeColor
        else:
            self.color=self.inactiveColor
    def on_touch_down(self,touch):
        if (self.active):
            return super(ButtonWithDisable,self).on_touch_down(touch)

Factory.register('ButtonWithDisable',cls=ButtonWithDisable)

class Spacer(FloatLayout):

    pass

Factory.register('Spacer', cls=Spacer)

class ListText(Label):

    pass

Factory.register('ListText',cls=ListText)

class AvailableTagList(BoxLayout):
    minWidth=NumericProperty(None)
    minHeight=NumericProperty(None)
    minSize=ReferenceListProperty(minWidth,minHeight)

    def CenterWhenContentSmaller(self):
        bound=self.minSize
        minW=bound[0]
        minH=bound[1]
        if len(self.children)==0:
            return
        self.width=max(self.children[0].width,minW)
        for row in self.children:
            tag=row.children[1]
            rank=row.children[0]
            row.width=max(row.width,minW)
            tag.width=row.width-rank.width
            tag.text_size[0]=tag.width-8
    
    def UpdateImageTags(self,info):
        #print "***update active tags in tag list for image***"
        search=self.registry['search']
        try:
            imgHash=info['hash']
        except:
            imgHash=None
        #print "info:",info
        #print "hash:",imgHash
        #print "tags:",self.image_tags
        for row in self.children:
            rank=row.children[0]
            rank.text="---"
            rank.color=colors['rankInactive']
            rank.bgHilight=rank.bgNormal
            tag=row.children[1]
            tag.bgHilight=tag.bgNormal
            tagText=tag.text
            if imgHash is None:
                color=colors['itemDisabled']
                rank.color=color
                tag.color=color
            else:
                try:
                    tag.bgHilight=colors['bgHilight']
                    hasTag=self.image_tags.index(tag.text)
                    color=colors['tagActive']
                    # get image's rank on this tag
                    imageList=search.GetRankedImageList(tag.text)
                    rankIdx=imageList.index(imgHash)
                    total=len(imageList)
                    # fRank 1.0=1st place, 0.0=last place
                    fRank=1.0
                    if (total>1):
                        fRank=1.0-float(rankIdx)/float(total-1)
                    rank.text=str(rankIdx+1)
                    rank.color=colors['rankGradient'](fRank)
                    rank.bgHilight=colors['bgHilight']
                except:
                    color=colors['tagInactive']
            tag.color=color

Factory.register('AvailableTagList',cls=AvailableTagList)

class TagRankLabel(Label):
    bgNormal=ListProperty(colors['bgRank'])
    bgHilight=ListProperty(colors['bgHilight'])
    bgColor=ListProperty(colors['bgRank'])
    
    pass
    
Factory.register('TagRankLabel',cls=TagRankLabel)

class TagLabel(Label):
    bgNormal=ListProperty(colors['bgNormal'])
    bgHilight=ListProperty(colors['bgHilight'])
    bgColor=ListProperty(colors['bgNormal'])
    
    pass

Factory.register('TagLabel',cls=TagLabel)

class AvailableTagRow(BoxLayout):

    def __init__(self,*args,**kwargs):
        super(AvailableTagRow,self).__init__(*args,**kwargs)
        self.orientation='horizontal'
        self.size_hint=(1,None)
        self.height=24

    def on_touch_down(self,touch):
        pos=touch.pos
        if self.collide_point(*pos):
            children=self.children
            parent=self.parent
            wRank=children[0]
            wLabel=children[1]
            tag=wLabel.text
            try:
                tagRank=int(wRank.text)
            except:
                tagRank=0
            main=parent.registry['main']
            search=parent.registry['search']
            image=main.registry['image']
            info=main.imageInfo
            try:
                imgHash=info['hash']
            except:
                imgHash=None
            imgTags=parent.image_tags
            
            if imgHash is not None and wLabel.collide_point(*pos):
                # tag cell clicked with image loaded
                # operation: add tag to image if not active,
                #            or remove tag from image if active
                #
                #        PS: if image is not currently indexed in DB
                #            it will be indexed so as to permit setting
                #            tags on the image
                
                # Image must be indexed for tagging to be possible so
                # ensure that image is indexed in DB if it is not already
                search.AutoIndex(info,auto=True)
                
                # use the color to determine user intention
                # independently of any synchornization issues
                # if he clicked on active-colored tag he wants
                # it removed and if he clicked on inactive-colored
                # tag he wants it added
                tagActive=(tuple(wLabel.color)==colors['tagActive'])
                if tagActive:
                    try:
                        idx=image.tags.index(tag)
                        del image.tags[idx]
                    except:
                        # wasn't really there
                        pass
                else:
                    try:
                        idx=image.tags.index(tag)
                    except:
                        # tags is not there already... Check!
                        image.tags.append(tag)
                imgTags=parent.image_tags
                
                # synchronize image tags in DB to new list
                search.SyncImageTags(info,imgTags)

                parent.UpdateImageTags(info)
            
            if tag in imgTags and wRank.collide_point(*pos):
                # rank cell clicked on active tag
                # operation: when not in 1st place promote image to top rank
                #            on tag, otherwise image is currently in 1st place
                #            on tag so bust it down to last place.
                pass

Factory.register('AvailableTagRow',cls=AvailableTagRow)

class ResultRowContainer(GridLayout):
    bgNormal=ListProperty(colors['bgNormal'])
    bgHilight=ListProperty(colors['bgHilight'])
    bgColor=ListProperty(colors['bgNormal'])

    def on_touch_down(self,touch):
        pos=touch.pos
        if self.collide_point(*pos):
            search=self.parent
            image=search.registry['image']
            hdg=search.registry['header']
            heads=hdg.children[8:]
            heads.reverse()
            info={}
            info['idx']=search.children.index(self)
            idx=0
            for c in reversed(self.children):
                c.color=colors['resultSelected']
                slot=heads[idx].text
                info[slot]=c.text
                idx=(idx+1)%8
            search.selected=info
        else:
            for c in self.children:
                c.color=colors['resultNormal']
        return False
    
    def Select(self):
        #print "*** selecting:",self.children[0].text
        search=self.parent
        image=search.registry['image']
        hdg=search.registry['header']
        heads=hdg.children[8:]
        heads.reverse()
        info={}
        info['idx']=search.children.index(self)
        for r in search.children:
            if r==self:
                color=colors['resultSelected']
            else:
                color=colors['resultNormal']
            if r!=hdg:
                idx=0
                for c in reversed(r.children):
                    c.color=color
                    if (r==self):
                        slot=heads[idx].text
                        info[slot]=c.text
                    idx=(idx+1)%8
        search.selected=info

Factory.register('ResultRowContainer',cls=ResultRowContainer)

class SortHeading(Label):

    def on_touch_down(self,touch):
        pos=touch.pos
        if self.collide_point(*pos):
            self.parent.parent.sorting=self.text
            return True
        return False

Factory.register('SortHeading',cls=SortHeading)

class SearchResults(BoxLayout):
    tHeader=StringProperty('ResultHeader')
    tRow=StringProperty('ResultRow')
    DataBase=ObjectProperty(None)
    DataProc=ObjectProperty(None)
    registry=DictProperty({})
    Query=StringProperty('')
    ordering=StringProperty('')
    tags=ListProperty([])
    bgColor=ListProperty(colors['bgNormal'])
    selected=DictProperty({})
    filterMode=OptionProperty('OR',options=['AND','OR','NOR'])
    filterClause=StringProperty('')
    filterPrams=DictProperty({})
    searchWhere=OptionProperty('name',options=['name','path'])
    searchText=StringProperty('')
    searchPrams=DictProperty({})
    sorting=StringProperty('')
    SortOrder=StringProperty('')

    def ApplySearch(self,src,where):
        text=src.text.replace("%","")
        src.text=text
        self.searchWhere=where
        self.searchText=text
        self.ApplyFilter()

    def ApplyFilter(self):
        """
        Updates search tag filter to new tags and
        filter mode (and sort column) and updates
        query appropriately
        """
        mode=self.filterMode
        ftags=self.registry['tag_filter'].children
        prams={}
        argprams=[]

        newprams={}
        newprams.update(self.searchPrams)

        idx=0
        for ft in ftags:
            if ft.filterState=='include':
                prams["f%s" % idx]=ft.text
                argprams.append(":f%s" % idx)
                idx+=1

        pfx='SELECT * FROM `ImageInfo` WHERE '
        lhs='ifnull(`Hash`=(SELECT `Hash` FROM `LabelledImageTags` WHERE `Hash`=ImageInfo.`Hash` AND ('
        rhs=') GROUP BY `Hash`),0)'
        hasTagTerm=False
        if len(argprams)<1:
            clause=pfx[:-6]
        else:
            hasTagTerm=True
            if mode=='AND':
                lhs=lhs[:-1]
                rhs='),0)'
                rept=lhs+"`Label`=%s"+rhs
                clause=' AND '.join([rept % x for x in argprams])
                clause=pfx+clause
            if mode=='OR' or mode=='NOR':
                clause=' OR '.join(["`Label`=%s" % x for x in argprams])
            if mode=='OR':
                clause=pfx+lhs+clause+rhs
            if mode=='NOR':
                clause=pfx+"NOT "+lhs+clause+rhs
        newprams.update(prams)

        if (self.searchText!=''):
            oper='AND'
            newprams['search']="%%%s%%" % self.searchText
            suf=clause[-6:].upper()
            try:
                cl_upr=clause.upper()
                idxWhere=cl_upr.index('WHERE')
            except:
                oper='WHERE'
            if clause[-1]!=" ":
                clause=clause+" "
            clause=clause+"%s `%s` LIKE :search" % (oper,{'name':'Name','path':'Path'}[self.searchWhere])

        if self.SortOrder!='' and self.SortOrder is not None:
            tokens=self.SortOrder.split("`")
            column=tokens[1]
            if column not in ['Tags']:
                clause=" ".join((clause,self.SortOrder))

        try:
            limit=int(self.limitOb.text)
        except:
            limit=0
        if limit<1:
            limit=100
        # cap limit to avoid sluggish performance
        if limit>1000:
            limit=1000
        self.limitOb.text=str(limit)
        clause=" ".join((clause,"LIMIT :limit"))
        newprams['limit']=limit
        
        self.searchPrams=newprams
        self.Query=""
        self.Query=clause
    
    def on_Query(self,who,query):    
        if query=="" or query is None:
            return

        conn=self.DataBase
        process=self.DataProc
        print "*** Query:",query
        print "*** Prams:",self.searchPrams
        
        process.execute(query,self.searchPrams)

        # clear result view
        self.ClearResults()
                
        results=process.fetchall()
        for row in results:
            #print row
            # Populate into result view
            info={
                'name'   : row[0],
                'width'  : int(row[1]),
                'height' : int(row[2]),
                'pixels' : FormatPixels(int(row[3])),
                'size'   : FormatBytes(int(row[4])),
                'tags'   : '',
                'hash'   : row[5],
                'path'   : row[6]
            }
            iTags=self.GetImageTags(info)
            info['tags']=','.join(iTags)
            ctx={'field':info}
            resultEntry=Builder.template('ResultRow',**ctx)
            self.add_widget(resultEntry)

    def UpdateFilterMode(self,idx,group):
        for i in range(len(group)):
            if idx==i:
                self.filterMode=['AND','OR','NOR'][idx]
                group[i].state='down'
            else:
                group[i].state='normal'

    def AddNewTag(self,label):
        tagList=self.registry['tags_avl']
        tagInput=self.registry['tag_input']
        #print "Add new tag to DB:",label
        self.tags.append(label)
        tagInput.text=''

    def DropTag(self,label):
        tagList=self.registry['tags_avl']
        tagInput=self.registry['tag_input']
        #print "Drop tag from DB:",label
        try:
            idx=self.tags.index(label)
        except:
            return
        del self.tags[idx]
        tagInput.text=''

    def AutoIndex(self,info,auto=None):
        """
        Index image into DB upon viewing if auto_index property is True
        or if image already in DB at path has been modified
        
        `auto` keyword can be set to True to
        perform an explicit indexing operation
        """
        #print "*** autoindex to DB:",self.auto_index
        conn=self.DataBase
        process=self.DataProc
        
        if auto is None:
            auto=self.auto_index
        
        row=self.LookupPathOrHash(info['path'],info['hash'])
        #print "row:",row
        if row is not None:
            dbHash=row[5]
            if dbHash!=info['hash']:
                #print "modify"
                process.execute(Queries.UpdateImageInfo,info)
                conn.commit()
        
        if auto and row is None:
            #print "insert"
            process.execute(Queries.StoreImageInfo,info)
            conn.commit()

    def SyncImageTags(self,info,tags):
        """
        Update DB tags of image in `info` to match
        tag list in `tags` either by inserting any
        tags not in the DB or deleting tags found
        in the DB that are not in `tags`
        """
        conn=self.DataBase
        process=self.DataProc
        try:
            imgHash=info['hash']
        except:
            return
        dbTags=self.GetImageTags(info)
        
        # insert pass
        for tag in tags:
            if tag not in dbTags:
                #print "*** insert tag:",tag
                process.execute(
                    Queries.InsertImageTag,
                    {'hash':info['hash'],'tag':tag})
        conn.commit()
        
        # delete pass
        for tag in dbTags:
            if tag not in tags:
                #print "*** delete tag:",tag
                process.execute(
                    Queries.DeleteImageTag,
                    {'hash':info['hash'],'tag':tag})
        conn.commit()

    def GetRankedImageList(self,tag):
        """
        Get list of images with argument tag ordered by rank
        """
        conn=self.DataBase
        process=self.DataProc
        result=[]
        
        process.execute(Queries.ImagesListedByRankHavingTag,{'Label':tag})
        row=process.fetchone()
        while row is not None:
            result.append(row[0])
            row=process.fetchone()
        
        return result

    def GetImageTags(self,info):
        """
        Returns the list of tags in DB for image in info
        """
        conn=self.DataBase
        process=self.DataProc
        tags=[]
        try:
            process.execute(Queries.LookupTags,info)
            row=process.fetchone()
            while row is not None:
                tags.append(row[0])
                row=process.fetchone()
        except:
            pass
        return tags
    
    def UpdateImageTagsFromDB(self,info):
        """
        Updates tags on loaded image to
        match those currently stored in DB
        """
        try:
            dbHash=info['hash']
        except:
            return
        #print "*** sync image with DB tags"
        image=self.registry['image']
        image.tags=self.GetImageTags(info)

    def LookupPathOrHash(self,path,theHash):
        conn=self.DataBase
        process=self.DataProc
        process.execute(Queries.LookupPathOrHash,{'Path':path,'Hash':theHash})
        row=process.fetchone()
        return row

    def PopulateAvailableTags(self,who):
        main=self.registry['main']
        tags=self.tags
        maxT=0
        moveListeners=main.moveListeners
        moveListeners['AvailableTags']=[]
        for tag in self.tags:
            maxT=max(maxT,len(tag))
        who.clear_widgets()
        for tag in self.tags:
            row=AvailableTagRow()
            row.size_hint=(None,None)
            row.height=25
            rowTag=TagLabel(text=tag)
            moveListeners['AvailableTags'].append(rowTag)
            row.width=10+(maxT+8)*rowTag.font_size
            rowTag.height=24
            rowTag.width=8+maxT*rowTag.font_size
            rowTag.size_hint=(None,None)
            rowTag.halign='left'
            rowTag.valign='middle'
            rowTag.text_size=(maxT*rowTag.font_size,24)
            rowRank=TagRankLabel(text='---')
            moveListeners['AvailableTags'].append(rowRank)
            rowRank.height=24
            rowRank.width=2+8*rowTag.font_size
            rowRank.size_hint=(None,None)
            rowRank.halign='center'
            rowRank.valign='middle'
            rowRank.text_size=(8*rowTag.font_size,24)
            row.add_widget(rowTag)
            row.add_widget(rowRank)
            who.add_widget(row)
        if len(self.tags)>0:
            who.width=who.children[0].width
            who.height=25*len(self.tags)

    def ClearResults(self):
        hdr=self.registry['header']
        main=self.registry['main']
        main.moveListeners['results']=[]
        for k in self.children[:]:
            if (hdr!=k):
                self.remove_widget(k)
        self.ComputeWidth()

    def SelectNextFile(self):
        """
        Selects next item in results
        """
        hdr=self.registry['header']
        children=self.children
        idx=-1
        count=len(children)-1
        #print "*** sel:",self.selected['Path']
        #print "*** count:",count
        for i in range(count):
            row=children[i]
            hkey=row.children[1].text
            if self.selected['Hash']==hkey:
                idx=i
        #print "*** cur idx",idx
        print children[idx].children[0].text
        if idx>=0:
            idx-=1
            if idx<0:
                idx+=count
            #print "*** new idx",idx
            sel=children[idx]
            #print sel.children[0].text
            sel.Select()

    def SelectPrevFile(self):
        """
        Selects prev item in results
        """
        hdr=self.registry['header']
        children=self.children
        idx=-1
        count=len(children)-1
        #print "*** sel:",self.selected['Path']
        #print "*** count:",count
        for i in range(count):
            row=children[i]
            hkey=row.children[1].text
            if self.selected['Hash']==hkey:
                idx=i
        #print "*** cur idx",idx
        #print children[idx].children[0].text
        if idx>=0:
            idx+=1
            if idx>=count:
                idx-=count
            print "*** new idx",idx
            sel=children[idx]
            print sel.children[0].text
            sel.Select()

    def on_tags(self,who,newTags):
        tagsAvl=self.registry['tags_avl']
        #print "*** Tags modified ***"
        # read database tagdefs
        dbTags=self.ReadTags()
        # check against DB tags for differences
        #print "Cur (DB):",dbTags
        #print "New dict:",newTags
        if dbTags!=newTags:
            conn=self.DataBase
            process=self.DataProc
            # perform inserts or deletes as needed
            # to match up the lists.  Note: tagids are NOT modified
            # with update to avoid key dupication and reference errors.
            curLabels=dbTags
            newLabels=newTags
            
            # delete pass
            # scan curLabels (DB) and delete any not in newLabels
            for label in curLabels:
                try:
                    newLabels.index(label)
                except:
                    #print "should delete %s: tag is in database but not in modified tags" % label
                    process.execute(Queries.DeleteTag,{'Label':label})
            
            # insert pass
            # scan newTags and insert any not in curLabels
            for label in newLabels:
                try:
                    curLabels.index(label)
                except:
                    #print "should insert %s: tag is in modified tags but not in database" % label
                    process.execute(Queries.InsertTag,{'Label':label})
            
            conn.commit()
            # reload database
            newTags=self.ReadTags()
            # set working tags to match database
            self.tags=newTags
        else:
            #print "database and modified tags match"
            pass
        # generates a tags-changed event on available tags widget
        self.PopulateAvailableTags(tagsAvl)
        tagsAvl.tag_change^=1
        

    def ComputeWidth(self):
        # determine largest width...
        width=0
        column_width={}
        for row in reversed(self.children):
            # ...per row
            row_width=0
            col=0
            for cell in reversed(row.children):
                # ...per column
                try:
                    cwidth=8+int(cell.font_size*len(cell.text))
                    if cell.parent==self.registry['header']:
                        # normalize extra space after header labels
                        # to account for sort direction character
                        last=cell.text[-1]
                        if last!='+' and last!='-':
                            cwidth+=cell.font_size
                    #print cwidth,cell.text
                except:
                    # this is one of the HR widgetss
                    cwidth=0
                if not column_width.has_key(col):
                    column_width[col]=cwidth
                else:
                    column_width[col]=max(50,column_width[col],cwidth)
                row_width+=cwidth
                col=(col+1)%8
            width=max(width,row_width)
        # normalize width of all cells in a column
        for row in reversed(self.children):
            row.width=width
            col=0
            for cell in reversed(row.children):
                cell.width=column_width[col]
                try:
                    cell.text_size=(cell.width-8,cell.height)
                except:
                    pass
                col=(col+1)%8
        width=width+232
        self.width=width
        #print "SearchResults new width:",width
        return width

    def OpenDB(self):
        db=os.path.join(self.dataDir,"imageinfo.db")
        conn=dbapi.connect(db)
        self.DataBase=conn
        process=conn.cursor()
        self.DataProc=process
        self.registry['main'].registerDB(conn,process)
        
        process.execute("PRAGMA foreign_keys=ON")
        process.execute(Queries.CreateTable['ImageInfo'])
        process.execute(Queries.CreateTable['ImageTags'])
        process.execute(Queries.CreateTable['Tags'])
        process.execute(Queries.RemoveView['LabelledImageTags'])
        process.execute(Queries.CreateView['LabelledImageTags'])
        
        self.tags=self.ReadTags()

    def ReadTags(self):
        tags={}
        conn=self.DataBase
        process=self.DataProc
        process.execute(Queries.ReadAll['Tags'])
        row=process.fetchone()
        while row is not None:
            (idx,label)=row
            tags[idx]=label
            row=process.fetchone()
        return tags.values()

    def ValidateTagInput(self,obInput,obAdd,obDelete):
        """
        Validate input tag in obInput.text
        
        If it matches an existing tag:
            disable obAdd
            enable  obDelete
            
        If it does not match existing tag:
            enable  obAdd
            disable obDelete
        
        Disable obAdd if tag is empty.
        """
        tags=self.ReadTags()
        inputTag=obInput.text
        exists=inputTag in tags
        if exists:
            obAdd.active=False
            obDelete.active=True
        else:
            if len(inputTag)>0:
                obAdd.active=True
            else:
                obAdd.active=False
            obDelete.active=False

    def SetSorting(self):
        sort=self.sorting
        if sort[-1]=='+' or sort[-1]=='-':
            sort=sort[:-1]
        hdr=self.registry['header']
        for c in hdr.children:
            try:
                txt=c.text
                order=txt[-1]
                if txt[-1]=='+' or txt[-1]=='-':
                    txt=txt[:-1]
                else:
                    order='-'
                if txt==sort:
                    if order=='+':
                        order='-'
                    else:
                        order='+'
                    sort=txt+order
                    c.text=sort
                    c.color=colors['sortedColumn']
                else:
                    order=''
                    c.text=txt
                    c.color=colors['normalColumn']
            except:
                pass
        # correct width of header elements
        self.ComputeWidth()
        #print "set sorting to",sort[:-1],{'-':'DESC','+':'ASC'}[sort[-1]]
        self.SortOrder="ORDER BY `%s` %s" % (sort[:-1],{'-':'DESC','+':'ASC'}[sort[-1]])
        self.ApplyFilter()

    def ViewSelectedImage(self):
        image=self.registry['image']
        which=self.selected
        image.focus=self
        image.source=which['Path']

Factory.register('SearchResults', cls=SearchResults)

class FileSelWrapper(FileChooserIconView):
    bgColor=ListProperty(colors['bgNormal'])

Factory.register('FileSelWrapper', cls=FileSelWrapper)

class ImageWithInfo(Image):
    pixelCount=NumericProperty(0)
    imageHash=StringProperty('')
    tags=ListProperty([])
    focus=ObjectProperty(None)
    focusReg=DictProperty({})
    
    def __init__(self,*args,**kwargs):
        super(ImageWithInfo,self).__init__(*args,**kwargs)
        self._kb=None
    
    def on_focus(self,who,what):
        files=self.registry['files']
        main=self.registry['main']
        if what==main:
            what=files
        if what not in [None, self]:
            self.focusReg[what]=1
            if self._kb is None:
                #print "aquire keyboard"
                self._kb=Window.request_keyboard(self._on_lost_keyboard,self)
                self._kb.bind(on_key_down=self._on_key_down)
        for ob in self.focusReg.keys():
            if ob==what:
                ob.bgColor=colors['bgBrowsing']
            else:
                ob.bgColor=colors['bgNormal']
    
    def _on_key_down(self,kb,key,text,mods):
        fileSel=self.registry['files']
        main=self.registry['main']
        keynm=key[1]
        f=self.focus
        if f==main:
            f=fileSel
        #print "*** key:",kb,repr(key),repr(text),repr(mods)
        if keynm=='escape':
            kb.release()
        try:
            if f in [fileSel]:
                    if keynm=='up':
                        f.SelectUpperFile()
                    if keynm=='down':
                        f.SelectLowerFile()
                    if keynm=='left':
                        f.SelectPrevFile()
                    if keynm=='right':
                        f.SelectNextFile()
            else:
                # for 1D lists L==U, D==R
                if keynm in ['up','left']:
                    f.SelectPrevFile()
                if keynm in ['down','right']:
                    f.SelectNextFile()
        except AttributeError:
            print "*** BUG *** %s.Select%sFile unimplemented"%(f.__class__.__name__,{'up':'Upper','down':'Lower','left':'Prev','right':'Next'}[keynm])
        return True
        
    def _on_lost_keyboard(self):
        #print "Lost keyboard"
        self._kb.unbind(on_key_down=self._on_key_down)
        self._kb=None
        self.focus=self
    
    def on_source(self,who,what):
        Window.set_title("ImageOrg Image Viewer/Organizer: %s" % os.path.basename(self.source))
    
    def on_texture(self,who,what):
        tex=self.texture
        #print "Image Texture change:",tex
        if tex is not None:
            self.obtainInfo()
            if self.registry is not None:
                main=self.registry['main']
                info={
                    'name'   : str(os.path.basename(self.source)),
                    'width'  : str(tex.size[0]),
                    'height' : str(tex.size[1]),
                    'pixels' : str(self.pixelCount),
                    'size'   : str(self.fileSize),
                    'tags'   : str([]),
                    'hash'   : str(self.imageHash),
                    'path'   : str(self.source)
                }
                main.imageInfo=info
                #print "*** sync with DB"
                search=self.registry['search']
                search.AutoIndex(info)
                search.UpdateImageTagsFromDB(info)
                tags=self.registry['tags']
                tags.UpdateImageTags(info)
                
        super(ImageWithInfo,self).on_texture(who,what)
    
    def obtainInfo(self):
        tex=self.texture
        self.pixelCount=tex.size[0]*tex.size[1]
        if (self.source is None or self.source==''):
            self.imageHash='da39a3ee5e6b4b0d3255bfef95601890afd80709'
            self.fileSize=0
        else:
            self.fileSize=os.path.getsize(self.source)
            f=open(self.source,'rb')
            #print "==      source:",self.source
            cur=0
            old=-1
            src=""
            while (cur!=old):
                old=cur
                src=src+f.read()
                cur=len(src)
            self.imageHash=hashlib.sha1(src).hexdigest()
            src=""
            #print "==  SHA-1 hash:",self.imageHash
            f.close()
        #print "== pixel count:",FormatPixels(self.pixelCount)

Factory.register('ImageWithInfo', cls=ImageWithInfo)

class MainWindow(FloatLayout):
    DataBase=ObjectProperty(None)
    DataProc=ObjectProperty(None)
    moveListeners=DictProperty({})
    
    def __init__(self,*args,**kwargs):
        super(MainWindow,self).__init__(*args,**kwargs)
        self.dataDir=kwargs['dataDir']
        Window.bind(mouse_pos=self.mouseMove)
        self.moveListeners['results']=[]

    def mouseMove(self,who,what):
        for groupId,group in self.moveListeners.iteritems():
            for ob in group:
                ob.bgColor=ob.bgNormal
                if ob.collide_point(*what):
                    ob.bgColor=ob.bgHilight

    def validateSelection(self,sel):
        image=self.registry['image']
        if len(sel)<1:
            return
        item=sel[0]
        if os.path.isdir(item):
            return
        if (self.curImage!=item):
            self.curImage=item
            image.focus=self

    def registerDB(self,dbConn,dbProc):
        self.DataBase=dbConn
        self.DataProc=dbProc


    def updateDrives(self):
        drives=[c+':\\' for c in string.lowercase if os.path.isdir(c+':\\')]
        drivesParent=self.registry['drives']
        if (drivesParent is not None):
            drivesParent.clear_widgets()
            for drive in drives:
                ctx={'text':drive,'target':self.registry['files']}
                drivesParent.add_widget(Builder.template('DriveButton',**ctx))

data=os.path.join(os.path.expanduser("~"),".ImageOrg")
# Create datadir if it doesn't exist
if not os.path.exists(data):
    try:
        os.mkdir(data)
    except:
        print "FATAL: Unable to create data directory."
        os.abort()
# Access the datadir (tests accessibility)
    if not os.access(data,os.F_OK,os.R_OK,os.W_OK):
        print "FATAL: Insufficient access to datadir:"
        if not os.access(data,os.R_OK):
            print "       Data directory is not readable."
        if not os.access(data,os.W_OK):
            print "       Data directory is not writable."
        os.abort()

# Source the kv ui template
Builder.load_file ('ImageOrg.kv')

class MyApp(App):
    def __init__(self,*args,**kwargs):
        super(MyApp,self).__init__(*args,**kwargs)
        self.dataDir=kwargs['dataDir']
        self.title="ImageOrg Image Viewer/Organizer"
    def build(self):
        main=MainWindow(dataDir=self.dataDir)
        tagsAvl=main.registry['tags']
        search=main.registry['search']
        search.dataDir=self.dataDir
        search.ComputeWidth()
        search.PopulateAvailableTags(tagsAvl)
        main.updateDrives()
        panel=main.registry['panel']
        panel.switch_to(panel.default_tab)
        return main

if __name__ == '__main__':
    MyApp(dataDir=data).run()
