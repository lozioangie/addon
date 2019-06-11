# -*- coding: utf-8 -*-
import hashlib

from core import httptools, filetools, downloadtools
from platformcode import logger, platformtools
import json
import xbmc
import re
import xbmcaddon

addon = xbmcaddon.Addon('plugin.video.kod')

_hdr_pat = re.compile("^@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@.*")

# branch = 'stable'
branch = 'updater'
# user = 'kodiondemand'
user = 'mac12m99'
repo = 'addon'
addonDir = xbmc.translatePath("special://home/addons/") + "plugin.video.kod/"
maxPage = 5  # le api restituiscono 30 commit per volta, quindi se si è rimasti troppo indietro c'è bisogno di andare avanti con le pagine
trackingFile = "last_commit.txt"


def loadCommits(page=1):
    apiLink = 'https://api.github.com/repos/' + user + '/' + repo + '/commits?sha=' + branch + "&page=" + str(page)
    commitsLink = httptools.downloadpage(apiLink).data
    logger.info(apiLink)
    return json.loads(commitsLink)


def check_addon_init():
    # if not addon.getSetting('addon_update_enabled'):
    #     return False
    commits = loadCommits()

    localCommitFile = open(addonDir+trackingFile, 'r+')
    localCommitSha = localCommitFile.read()
    localCommitSha = localCommitSha.replace('\n','') # da testare
    updated = False

    pos = None
    page = 1
    while commits and page <= maxPage:
        for n, c in enumerate(commits):
            if c['sha'] == localCommitSha:
                pos = n
                break
        else:
            page += 1
            commits = loadCommits(page)

        break
    else:
        logger.info('Impossibile trovare il commit attuale')

    if pos > 0:
        for c in reversed(commits[:pos]):
            commit = httptools.downloadpage(c['url']).data
            commitJson = json.loads(commit)
            alreadyApplied = True

            for file in commitJson['files']:
                if file["filename"] == trackingFile:  # il file di tracking non si modifica
                    continue
                else:
                    if file['status'] == 'modified' or file['status'] == 'added':
                        if 'patch' in file:
                            text = ""
                            try:
                                localFile = open(addonDir + file["filename"], 'r+')
                                for line in localFile:
                                    text += line
                            except IOError: # nuovo file
                                localFile = open(addonDir + file["filename"], 'w')

                            patched = apply_patch(text, (file['patch']+'\n').encode('utf-8'))
                            if patched != text:  # non eseguo se già applicata (es. scaricato zip da github)
                                if getSha(patched) == file['sha']:
                                    localFile.seek(0)
                                    localFile.truncate()
                                    localFile.writelines(patched)
                                    localFile.close()
                                    alreadyApplied = False
                                else:  # nel caso ci siano stati problemi
                                    downloadtools.downloadfile(file['raw_url'], addonDir + file['filename'],
                                                               silent=True)
                        else:  # è un file NON testuale, lo devo scaricare
                            # se non è già applicato
                            if not (filetools.isfile(addonDir + file['filename']) and getSha(
                                    filetools.read(addonDir + file['filename']) == file['sha'])):
                                downloadtools.downloadfile(file['raw_url'], addonDir + file['filename'], silent=True)
                                alreadyApplied = False
                    elif file['status'] == 'removed':
                        try:
                            filetools.remove(addonDir+file["filename"])
                            alreadyApplied = False
                        except:
                            pass
                    elif file['status'] == 'renamed':
                        # se non è già applicato
                        if not (filetools.isfile(addonDir + file['filename']) and getSha(
                                filetools.read(addonDir + file['filename']) == file['sha'])):
                            dirs = file['filename'].split('/')
                            for d in dirs[:-1]:
                                if not filetools.isdir(addonDir + d):
                                    filetools.mkdir(addonDir + d)
                            filetools.move(addonDir + file['previous_filename'], addonDir + file['filename'])
                            alreadyApplied = False

            if not alreadyApplied:  # non mando notifica se già applicata (es. scaricato zip da github)
                platformtools.dialog_notification('Kodi on Demand', commitJson['commit']['message'])

        localCommitFile.seek(0)
        localCommitFile.truncate()
        localCommitFile.writelines(c['sha'])
        localCommitFile.close()

    else:
        logger.info('Nessun nuovo aggiornamento')

    return updated


def calcCurrHash():
    from lib import githash
    treeHash = githash.tree_hash(addonDir).hexdigest()
    commits = loadCommits()
    page = 1
    while commits and page <= maxPage:
        for n, c in enumerate(commits):
            if c['tree']['sha'] == treeHash:
                localCommitFile = open(addonDir + trackingFile, 'w')
                localCommitFile.write(c['sha'])
                localCommitFile.close()
                break
        else:
            page += 1
            commits = loadCommits(page)

        break


# https://gist.github.com/noporpoise/16e731849eb1231e86d78f9dfeca3abc  Grazie!

def apply_patch(s,patch,revert=False):
  """
  Apply unified diff patch to string s to recover newer string.
  If revert is True, treat s as the newer string, recover older string.
  """
  s = s.splitlines(True)
  p = patch.splitlines(True)
  t = ''
  i = sl = 0
  (midx,sign) = (1,'+') if not revert else (3,'-')
  while i < len(p) and p[i].startswith(("---","+++")): i += 1 # skip header lines
  while i < len(p):
    m = _hdr_pat.match(p[i])
    if not m: raise Exception("Cannot process diff")
    i += 1
    l = int(m.group(midx))-1 + (m.group(midx+1) == '0')
    t += ''.join(s[sl:l])
    sl = l
    while i < len(p) and p[i][0] != '@':
      if i+1 < len(p) and p[i+1][0] == '\\': line = p[i][:-1]; i += 2
      else: line = p[i]; i += 1
      if len(line) > 0:
        if line[0] == sign or line[0] == ' ': t += line[1:]
        sl += (line[0] != sign)
  t += ''.join(s[sl:])
  return t


def getSha(fileText):
    return hashlib.sha1("blob " + str(len(fileText)) + "\0" + fileText).hexdigest()