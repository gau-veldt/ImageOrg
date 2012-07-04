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

CreateTable={
    
"ImageInfo":"\
CREATE TABLE IF NOT EXISTS `ImageInfo` (\
 `Name` TEXT NOT NULL,\
 `Width` INTEGER NOT NULL,\
 `Height` INTEGER NOT NULL,\
 `Pixels` INTEGER NOT NULL,\
 `Size` INTEGER NOT NULL,\
 `Hash` TEXT NOT NULL,\
 `Path` TEXT NOT NULL,\
 PRIMARY KEY (`Hash`),\
 UNIQUE (`Path`)\
)",

"Tags":"\
CREATE TABLE IF NOT EXISTS `Tags` (\
 `TagID` INTEGER PRIMARY KEY,\
 `Label` TEXT NOT NULL\
)",

"ImageTags":"\
CREATE TABLE IF NOT EXISTS `ImageTags` (\
`TagID` INTEGER NOT NULL REFERENCES `Tags` ON DELETE CASCADE ON UPDATE CASCADE,\
`Hash` TEXT NOT NULL REFERENCES `ImageInfo` ON DELETE CASCADE ON UPDATE CASCADE,\
`Weight` INT NOT NULL,\
 UNIQUE (`TagID`,`Hash`),\
 UNIQUE (`TagID`,`Weight`)\
)",

}

RemoveView={

"LabelledImageTags":"\
DROP VIEW IF EXISTS `LabelledImageTags`\
"

}

CreateView={

"LabelledImageTags":"\
CREATE VIEW `LabelledImageTags` AS \
SELECT \
(SELECT `Label` FROM `Tags` WHERE `Tags`.TagID=`ImageTags`.TagID) AS `Label`,\
`Hash`,\
`Weight` \
FROM ImageTags\
"

}

ReadAll={
    "Tags" : "SELECT * from `Tags`"
}

InsertTag="INSERT INTO `Tags` (`Label`) VALUES (:Label)"
DeleteTag="DELETE FROM `Tags` WHERE `Label`=:Label"

LookupPathOrHash="SELECT * FROM `ImageInfo` WHERE `Path`=:Path or `Hash`=:Hash"
LookupTags="SELECT (SELECT `Label` FROM `Tags` WHERE `ImageTags`.`TagID`=`Tags`.`TagID`) AS `Label`,`Hash`,`Weight` FROM `ImageTags` WHERE `Hash`=:hash"

StoreImageInfo="INSERT INTO `ImageInfo`\
 (`Name`,`Width`,`Height`,`Pixels`,`Size`,`Hash`,`Path`)\
 VALUES (:name,:width,:height,:pixels,:size,:hash,:path)"
UpdateImageInfo="UPDATE `ImageInfo` SET\
 `Name`=:name,\
 `Width`=:width,\
 `Height`=:height,\
 `Pixels`=:pixels,\
 `Size`=:size,\
 `Hash`=:hash,\
 `Path`=:path\
 WHERE `Path`=:path"

ImagesListedByRankHavingTag="SELECT `Hash` FROM `ImageTags` WHERE\
 TagID=(SELECT `TagID` FROM `Tags` WHERE `Label`=:Label)\
 ORDER BY `Weight` ASC"
InsertImageTag="INSERT INTO `ImageTags` (`Hash`,`TagID`,`Weight`)\
 VALUES\
 (:hash,\
 (SELECT `TagID` FROM `Tags` WHERE `Label`=:tag),\
 (SELECT 1+ifnull(max(`Weight`),0) FROM `ImageTags` WHERE\
 `TagID`=(SELECT `TagID` FROM `Tags` WHERE `Label`=:tag))\
)"
DeleteImageTag="DELETE FROM `ImageTags` WHERE\
 `Hash`=:hash AND\
 `TagID`=(SELECT `TagID` FROM `Tags` WHERE `Label`=:tag)"

def SortClause(columnLabel):
    # returns a list of form: ['clause',{parms}]
    if "+-".find(columnLabel)>=0:
        # columnLabel is '' '+' or '-'
        return ['',{}]
    sortDir=columnLabel[-1]
    if "+-".find(sortDir)<0:
        # columnLabel with no '+' nor '-'
        sortDir='+'
        column=columnLabel
    else:
        # columnLabel stripped of '+' or '-'
        column=columnLabel[:-1]
    return ["ORDER BY :sortColumn "+{'+':'ASC','-':'DESC'}[sortDir],{'sortColumn':[column]}]
