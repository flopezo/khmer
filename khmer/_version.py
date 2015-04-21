from __future__ import print_function

# This file helps to compute a version number in source trees obtained from
# git-archive tarball (such as those provided by githubs download-from-tag
# feature). Distribution tarballs (built by setup.py sdist) and build
# directories (produced by setup.py build) will contain a much shorter file
# that just contains the computed version number.

# This file is released into the public domain. Generated by
# versioneer-0.14 (https://github.com/warner/python-versioneer)

import errno
import os
import re
import subprocess
import sys

# these strings will be replaced by git during git-archive
git_refnames = "$Format:%d$"
git_full = "$Format:%H$"

# these strings are filled in when 'setup.py versioneer' creates _version.py
tag_prefix = "v"
parentdir_prefix = "."
versionfile_source = "khmer/_version.py"


def run_command(commands, args, cwd=None, verbose=False, hide_stderr=False):
    assert isinstance(commands, list)
    p = None
    for c in commands:
        try:
            # remember shell=False, so use git.cmd on windows, not just git
            p = subprocess.Popen([c] + args, cwd=cwd, stdout=subprocess.PIPE,
                                 stderr=(subprocess.PIPE if hide_stderr
                                         else None))
            break
        except EnvironmentError:
            e = sys.exc_info()[1]
            if e.errno == errno.ENOENT:
                continue
            if verbose:
                print("unable to run %s" % args[0])
                print(e)
            return None
    else:
        if verbose:
            print("unable to find command, tried %s" % (commands,))
        return None
    stdout = p.communicate()[0].strip()
    if sys.version_info[0] >= 3:
        stdout = stdout.decode()
    if p.returncode != 0:
        if verbose:
            print("unable to run %s (error)" % args[0])
        return None
    return stdout


def versions_from_parentdir(parentdir_prefix, root, verbose=False):
    # Source tarballs conventionally unpack into a directory that includes
    # both the project name and a version string.
    dirname = os.path.basename(root)
    if not dirname.startswith(parentdir_prefix):
        if verbose:
            print("guessing rootdir is '%s', but '%s' doesn't start with "
                  "prefix '%s'" % (root, dirname, parentdir_prefix))
        return None
    return {"version": dirname[len(parentdir_prefix):], "full": ""}


def git_get_keywords(versionfile_abs):
    # the code embedded in _version.py can just fetch the value of these
    # keywords. When used from setup.py, we don't want to import _version.py,
    # so we do it with a regexp instead. This function is not used from
    # _version.py.
    keywords = {}
    try:
        f = open(versionfile_abs, "r")
        for line in f.readlines():
            if line.strip().startswith("git_refnames ="):
                mo = re.search(r'=\s*"(.*)"', line)
                if mo:
                    keywords["refnames"] = mo.group(1)
            if line.strip().startswith("git_full ="):
                mo = re.search(r'=\s*"(.*)"', line)
                if mo:
                    keywords["full"] = mo.group(1)
        f.close()
    except EnvironmentError:
        pass
    return keywords


def git_versions_from_keywords(keywords, tag_prefix, verbose=False):
    if not keywords:
        return {}  # keyword-finding function failed to find keywords
    refnames = keywords["refnames"].strip()
    if refnames.startswith("$Format"):
        if verbose:
            print("keywords are unexpanded, not using")
        return {}  # unexpanded, so not in an unpacked git-archive tarball
    refs = set([r.strip() for r in refnames.strip("()").split(",")])
    # starting in git-1.8.3, tags are listed as "tag: foo-1.0" instead of
    # just "foo-1.0". If we see a "tag: " prefix, prefer those.
    TAG = "tag: "
    tags = set([r[len(TAG):] for r in refs if r.startswith(TAG)])
    if not tags:
        # Either we're using git < 1.8.3, or there really are no tags. We use
        # a heuristic: assume all version tags have a digit. The old git %d
        # expansion behaves like git log --decorate=short and strips out the
        # refs/heads/ and refs/tags/ prefixes that would let us distinguish
        # between branches and tags. By ignoring refnames without digits, we
        # filter out many common branch names like "release" and
        # "stabilization", as well as "HEAD" and "master".
        tags = set([r for r in refs if re.search(r'\d', r)])
        if verbose:
            print("discarding '%s', no digits" % ",".join(refs - tags))
    if verbose:
        print("likely tags: %s" % ",".join(sorted(tags)))
    for ref in sorted(tags):
        # sorting will prefer e.g. "2.0" over "2.0rc1"
        if ref.startswith(tag_prefix):
            r = ref[len(tag_prefix):]
            if verbose:
                print("picking %s" % r)
            return {"version": r,
                    "full": keywords["full"].strip()}
    # no suitable tags, so version is "0+unknown", but full hex is still there
    if verbose:
        print("no suitable tags, using unknown + full revision id")
    return {"version": "0+unknown",
            "full": keywords["full"].strip()}


def git_parse_vcs_describe(git_describe, tag_prefix, verbose=False):
    # TAG-NUM-gHEX[-dirty] or HEX[-dirty] . TAG might have hyphens.

    # dirty
    dirty = git_describe.endswith("-dirty")
    if dirty:
        git_describe = git_describe[:git_describe.rindex("-dirty")]
    dirty_suffix = ".dirty" if dirty else ""

    # now we have TAG-NUM-gHEX or HEX

    if "-" not in git_describe:  # just HEX
        return "0+untagged.g" + git_describe + dirty_suffix, dirty

    # just TAG-NUM-gHEX
    mo = re.search(r'^(.+)-(\d+)-g([0-9a-f]+)$', git_describe)
    if not mo:
        # unparseable. Maybe git-describe is misbehaving?
        return "0+unparseable" + dirty_suffix, dirty

    # tag
    full_tag = mo.group(1)
    if not full_tag.startswith(tag_prefix):
        if verbose:
            fmt = "tag '%s' doesn't start with prefix '%s'"
            print(fmt % (full_tag, tag_prefix))
        return None, dirty
    tag = full_tag[len(tag_prefix):]

    # distance: number of commits since tag
    distance = int(mo.group(2))

    # commit: short hex revision ID
    commit = mo.group(3)

    # now build up version string, with post-release "local version
    # identifier". Our goal: TAG[+NUM.gHEX[.dirty]] . Note that if you get a
    # tagged build and then dirty it, you'll get TAG+0.gHEX.dirty . So you
    # can always test version.endswith(".dirty").
    version = tag
    if distance or dirty:
        version += "+%d.g%s" % (distance, commit) + dirty_suffix

    return version, dirty


def git_versions_from_vcs(tag_prefix, root, verbose=False):
    # this runs 'git' from the root of the source tree. This only gets called
    # if the git-archive 'subst' keywords were *not* expanded, and
    # _version.py hasn't already been rewritten with a short version string,
    # meaning we're inside a checked out source tree.

    if not os.path.exists(os.path.join(root, ".git")):
        if verbose:
            print("no .git in %s" % root)
        return {}  # get_versions() will try next method

    GITS = ["git"]
    if sys.platform == "win32":
        GITS = ["git.cmd", "git.exe"]
    # if there is a tag, this yields TAG-NUM-gHEX[-dirty]
    # if there are no tags, this yields HEX[-dirty] (no NUM)
    stdout = run_command(GITS, ["describe", "--tags", "--dirty",
                                "--always", "--long"],
                         cwd=root)
    # --long was added in git-1.5.5
    if stdout is None:
        return {}  # try next method
    version, dirty = git_parse_vcs_describe(stdout, tag_prefix, verbose)

    # build "full", which is FULLHEX[.dirty]
    stdout = run_command(GITS, ["rev-parse", "HEAD"], cwd=root)
    if stdout is None:
        return {}
    full = stdout.strip()
    if dirty:
        full += ".dirty"

    return {"version": version, "full": full}


def get_versions(default={"version": "0+unknown", "full": ""}, verbose=False):
    # I am in _version.py, which lives at ROOT/VERSIONFILE_SOURCE. If we have
    # __file__, we can work backwards from there to the root. Some
    # py2exe/bbfreeze/non-CPython implementations don't do __file__, in which
    # case we can only use expanded keywords.

    keywords = {"refnames": git_refnames, "full": git_full}
    ver = git_versions_from_keywords(keywords, tag_prefix, verbose)
    if ver:
        return ver

    try:
        root = os.path.realpath(__file__)
        # versionfile_source is the relative path from the top of the source
        # tree (where the .git directory might live) to this file. Invert
        # this to find the root from __file__.
        for i in versionfile_source.split('/'):
            root = os.path.dirname(root)
    except NameError:
        return default

    return (git_versions_from_vcs(tag_prefix, root, verbose)
            or versions_from_parentdir(parentdir_prefix, root, verbose)
            or default)
