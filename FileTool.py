import sublime
import sublime_plugin
import os
import functools
import time

import sublime, sublime_plugin
from collections import deque

import sys

class RenameFileCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if self.view.file_name() == None:
            return
        else:
            branch, leaf = os.path.split(self.view.file_name())
            v = self.view.window().show_input_panel("New Name:", leaf, functools.partial(self.on_done, self.view.file_name(), branch), None, None)
            name, ext = os.path.splitext(leaf)
            v.sel().clear()
            v.sel().add(sublime.Region(0, len(name)))
            
    def on_done(self, old, branch, leaf):
        new = os.path.join(branch, leaf)

        try:
            os.rename(old, new)
            v = self.view.window().find_open_file(old)
            if v:
                v.retarget(new)
        except:
            e = sys.exc_info()
            sublime.status_message("Unable to rename")
            
    def is_enabled(self):
        if self.view == None:
            return False
        return self.view.file_name() != None

MAX_SIZE = 64
LINE_THRESHOLD = 2

class Location(object):
    """A location in the history
    """

    def __init__(self, path, line, col):
        self.path = path
        self.line = line
        self.col = col
    
    def __eq__(self, other):
        return self.path == other.path and self.line == other.line
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __nonzero__(self):
        return (self.path is not None and self.line is not None)

    def near(self, other):
        return self.path == other.path and abs(self.line - other.line) <= LINE_THRESHOLD

    def copy(self):
        return Location(self.path, self.line, self.col)

class History(object):
    """Keep track of the history for a single window
    """

    def __init__(self, max_size=MAX_SIZE):
        self._current = None                # current location as far as the
                                            # history is concerned
        self._back = deque([], max_size)    # items before self._current
        self._forward = deque([], max_size) # items after self._current
        
        self._last_movement = None          # last recorded movement
    
    def record_movement(self, location):
        """Record movement to the given location, pushing history if
        applicable
        """
        if location:
            if self.has_changed(location):
                self.push(location)
            self.mark_location(location)

    def mark_location(self, location):
        """Remember the current location, for the purposes of being able
        to do a has_changed() check.
        """
        self._last_movement = location.copy()
    
    def has_changed(self, location):
        """Determine if the given location combination represents a
        significant enough change to warrant pushing history.
        """
        return self._last_movement is None or not self._last_movement.near(location)
    
    def push(self, location):
        """Push the given location to the back history. Clear the forward
        history.
        """

        if self._current is not None:
            self._back.append(self._current.copy())
        self._current = location.copy()
        self._forward.clear()

    def back(self):
        """Move backward in history, returning the location to jump to.
        Returns None if no history.
        """

        if not self._back:
            return None
        
        self._forward.appendleft(self._current)        
        self._current = self._back.pop()
        self._last_movement = self._current # preempt, so we don't re-push
        return self._current

    def forward(self):
        """Move forward in history, returning the location to jump to.
        Returns None if no history.
        """

        if not self._forward:
            return None
        
        self._back.append(self._current)
        self._current = self._forward.popleft()
        self._last_movement = self._current # preempt, so we don't re-push
        return self._current

_histories = {} # window id -> History

def get_history():
    """Get a History object for the current window,
    creating a new one if required
    """

    window = sublime.active_window()
    if window is None:
        return None

    window_id = window.id()
    history = _histories.get(window_id, None)
    if history is None:
        _histories[window_id] = history = History()
    return history

class NavigationHistoryRecorder(sublime_plugin.EventListener):
    """Keep track of history
    """
    def on_selection_modified(self, view):
        """When the selection is changed, possibly record movement in the
        history
        """        
        history = get_history()
        tm = time.time()
        if history is None:
            return

        # use active_view to get the real sel view!
        view = sublime.active_window().active_view()
        path = view.file_name()

        # do not record pages that not exist on disk
        if path == None:
            return

        row, col = view.rowcol(view.sel()[0].a)
        history.record_movement(Location(path, row + 1, col + 1))

class NavigationHistoryBack(sublime_plugin.TextCommand):
    """Go back in history
    """

    def run(self, edit):
        history = get_history()
        if history is None:
            return            

        location = history.back()
        if location:
            is_view_open = False
            window = sublime.active_window()
            for view in window.views():
                if view.file_name() == location.path:
                    is_view_open = True
                    break

            while(os.path.isfile(location.path)==False and is_view_open==False):
                location = history.back()
                if location is None:
                    return

            window = sublime.active_window()
            window.open_file("%s:%d:%d" % (location.path, location.line, location.col), sublime.ENCODED_POSITION)

class NavigationHistoryForward(sublime_plugin.TextCommand):
    """Go forward in history
    """

    def run(self, edit):
        history = get_history()
        if history is None:
            return

        location = history.forward()
        if location:
            is_view_open = False
            window = sublime.active_window()
            for view in window.views():
                if view.file_name() == location.path:
                    is_view_open = True
                    break

            while(os.path.isfile(location.path)==False and is_view_open==False):
                location = history.forward()
                if location is None:
                    return

            window = sublime.active_window()
            window.open_file("%s:%d:%d" % (location.path, location.line, location.col), sublime.ENCODED_POSITION)