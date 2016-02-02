#
# Copyright 2016 Badi' Abdul-Wahid
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#
# Author: Badi' Abdul-Wahid <badi@iu.edu>
# Organization: Indiana University / FutureSystems
#




from __future__ import absolute_import

import traits.api as T
from traits.api import HasTraits

import networkx as nx
import time
import uuid
from functools import wraps
from concurrent import futures
from multiprocessing import cpu_count
from collections import OrderedDict


__doc__ = """\
Description
===========

This module provides an api for building a workflow graph of labeled
functions which can then be evaluated. Nodes connected with a desired
ordering or run sequentially, others can be run in parallel.

Syntax is inspired by the parallel (||) and sequential (;) operators.
For example:

::

  (A || B) ; (C || D)

means that A and B can be evaluated in parallel, and likewise C and D,
but both A and B must be completed before C or D may begin.

The python implementation overrides the bitwise **OR** (|) and **AND**
(&) operators to provide a similar syntactic feel. The example above
should be defined as such:

::

  (A() | B()) & (C() | D())

.. note::

  The python operator precedence for ``|`` and ``&`` is unchanged:
  ``&`` has higher precedence than ``|``.

Usage
=====

The first part is to mark top-level functions as :func:`delayed`.  The
``@delayed()`` decoration wraps the function so that calling the
function inserts the :class:`Node`, without applying the parameters,
into the call :class:`Graph`. You can access the ``graph`` property of
any node to get the current call graph.

For instance

.. code-block :: python

  @delayed()
  def A(x): print x*2

  @delayed()
  def B(x, y): return x ** y

  def main():
    node = A(24) | B(40, 2)


Once the graph has been built, it must be explicitly evaluated

.. code-block :: python

  evaluate(node.graph)

"""




__all__ = [
    'delayed', 'evaluate',
    'Node', 'OpNode', 'AndNode', 'OrNode', 'Graph',
]

class Graph(nx.DiGraph):
    """A NetworkX :func:`networkx.DiGraph` where the ordering of edges/nodes is
    preserved

    """

    node_dict_factory = OrderedDict
    adjlist_dict_factory = OrderedDict


TExecutor = T.Trait(futures.Executor)


def nodeid():
    """Generate a new node id

    :returns: node id
    :rtype: :class:`uuid.UUID`

    """

    return uuid.uuid4()


class delayed(object):
    """A :class:`delayed` is a decorator that delays evaluation of a function
    until explicitly called for using :func:`evaluate`.

    Intended usage: decorate a function such that :meth:`~object.__call__`\
    ing it returns a :class:`Node` instance that can be combined with
    other :class:`Node` instances using the bitwise :meth:`~object.__and__`
    (``&``) and :meth:`~object.__or__` (``|``) operators to create a workflow.

    """

    def __init__(self, graph=None, **kws):
        self.G = graph
        self.kws = kws

    def __call__(self, f):

        @wraps(f)
        def g(*args, **kwargs):
            return Node((f, args, kwargs),
                        graph=self.G,
                        **self.kws)

        return g


def find_root_node(graph):
    """:class:`Graph` -> :class:`Node`

    Find the root node of a connected DAG

    :rtype: :class:`Node`
    """

    i = nx.topological_sort(graph)[0]
    n = graph.node[i]['node']
    return n


def evaluate(graph):
    """:class:`Graph` -> IO ()

    Starting from the root node, evaluate the branches.
    The graph nodes are updated in-place.
    """

    # FIXME assert componenets(graph) == 1
    node = find_root_node(graph)
    node.eval()


class Node(HasTraits):
    """A node in the :class:`Graph` and associated state.

    :class:`Node`\ s can be composed using bitwise :meth:`~object.__and__` and
    :meth:`~object.__or__` operators to denote sequential or parallel
    evaluation order, respectively.

    For example, give ``A``, ``B``, and ``C`` functions that have been
    lifted to a :class:`Node` type (eg through the :class:`delayed`
    decorator ``@delayed()``), to evaluate ``A`` and ``B`` in parallel,
    then ``C``:

    .. code-block:: python

      G = (  (A(argA0, argA1) | B()) & C(argC)  ).graph

    will create the call :class:`Graph` ``G``.
    In order to evaluate ``G``:

    .. code-block:: python

      evaluate(G)

    """

    id = T.Trait(uuid.UUID)
    """The node id. This is also the key to find the node in the
    :class:`Graph`."""

    graph = T.Trait(Graph)
    """The call :class:`Graph` in which the node is located"""

    executor = T.Trait(futures.ThreadPoolExecutor)
    """The execution context for evaluating this node (see eg
    :class:`~concurrent.futures.ThreadPoolExecutor`)

    """

    timeout = T.Any()
    """How long to wait for execution to complete. See also
    :meth:`~concurrent.futures.Future.result`.

    """

    f = T.Function()
    """The function to evaluate"""

    name = T.String()
    """Name of the function, usually short for ``self.f.func_name``"""

    result = T.Trait(futures.Future)
    # The explicit link to `Future` is done because intersphince does
    # not find it
    """The concurrent.futures.Future_ containing result of the evaluation.

    .. _concurrent.futures.Future: https://pythonhosted.org/futures/index.html#future-objects

    """
    
    def __init__(self, (f, args, kws), graph=None, executor=None,
                 timeout=None, type=None):
        """Create a :class:`Node` to evaluate a function ``f`` in some
        ``graph`` using a given ``executor``

        :param (f, args, kws): the function to evaluate (any
                               callabled) along with positional and
                               keywork arguments.

        :param graph: The :class:`Graph` in which to insert the node
                      upon composition with others. A value of
                      ``None`` will create a new graph. When composed
                      with another node in a different
                      :func:`Node.graph` the two graphs with be
                      merged.

        :param executor: a :class:`futures.Executor` instance
        :param timeout: seconds (float or int) to wait.
        :param type: FIXME
        """
        self.id = nodeid()
        self.f = f
        self._args = args
        self._kws = kws
        self.name = f.func_name
        self.graph = graph
        self.executor = executor or futures.ThreadPoolExecutor(cpu_count())
        self.timeout = timeout


    def _init_graph(self, graph=None):
        """Initialize the `graph` attribute

        Create a :class:`Graph` for this node if necessary.

        :param graph: the :class:`Graph` to use if ours is ``None``
        """
        if self.graph is None and graph is None:
            self.graph = Graph()

        elif self.graph is None and graph is not None:
            self.graph = graph


    def _merge_graph(self, other):
        """Combine this :class:`Node`'s graph with ``other``'s :class:`Graph`.

        .. node::
          This updates ``this.graph`` **in-place**

        :param other: another instance of :class:`Node`
        """

        if not self.graph == other.graph:
            for s, t, data in other.graph.edges_iter(data=True):
                sn = other.graph.node[s]
                tn = other.graph.node[t]
                self.graph.add_node(s, sn)
                self.graph.add_node(t, tn)
                self.graph.add_edge(s, t, data)
            other.graph = self.graph


    @property
    def children_iter(self):
        """Generator of :class:`Node`\ s

        This ``yield``'s all the children :class:`Node`\ s of this node.

        :returns: Child nodes of this node.
        :rtype: generator of :class:`Node`
        """

        edges = set(self.graph.edges())
        for i in self.graph.successors_iter(self.id):
            child = self.graph.node[i]['node']
            assert (self.id, i) in edges
            yield child

    @property
    def children(self):
        """[:class:`Node`]

        The children of this node.
        See :func:`Node.children_iter`

        :rtype: list of :class:`Node`
        """
        return list(self.children_iter)


    def start(self):
        """Start evaluating this node

        Start evaluating this nodes function ``self.f`` if it hasn't
        already started.
        """
        

        if self.result is None:
            self.result = self.executor.submit(self.f, *self._args, **self._kws)
        else:
            # already started
            pass


    def wait(self):
        """Wait for this node to finish evaluating

        This may timeout if :func:`Node.timeout` is specified.
        """
        self.result.result(self.timeout)


    def eval(self):
        """Start and wait for a node."""
        self.start()
        self.wait()


    def compose(self, other, MkOpNode):
        """Compose this :class:`Node` with another Node.

        Two Nodes are composed using a proxy :class:`OpNode`.  The
        OpNode defines the evaluation semantics of its child nodes (eg
        sequantial or parallel).

        :param other: a :class:`Node`

        :param MkOpNode: a callable with keyword arg graph constructor
                         for the proxy node

        :returns: The proxy node with this node and other node as
                  children

        :rtype: :class:`OpNode`

        """

        self._init_graph()
        other._init_graph(self.graph)
        self._merge_graph(other)

        assert self.graph is not None, self.name
        assert other.graph is not None, other.name
        assert self.graph == other.graph
        G = self.graph

        # print self.name, operator, other.name

        s, t = self.id, other.id
        other.id = t
        op = MkOpNode(graph=G)
        G.add_node(op.id, node=op, label=op.name)
        G.add_node(s, node=self, label=self.name)
        G.add_node(t, node=other, label=other.name)
        G.add_edge(op.id, s)
        G.add_edge(op.id, t)

        return op


    def __and__(self, other):
        """Sequential composition

        :param other: the :class:`Node` to evaluate **after** this
                      :class:`Node`

        :returns: the node composition (see :func:`Node.compose`)
        :rtype: :class:`OpNode`

        """

        return self.compose(other, AndNode)


    def __or__(self, other):
        """Parallel composition

        :param other: The :class:`Node to evaluate along with this
                      :class:`Node`.

        :returns: the node composition (see :func:`Node.compose`)
        :rtype: :class:`OpNode`

        """

        return self.compose(other, OrNode)



class OpNode(Node):
    """A proxy node defining the evaluation semantics of its children
    :class:`Node`\ s

    Intended usage: this class it not intended to be instantiated
    directly. Rather, classes should inherit from :class:`OpNode` to
    defined the desired semantics.

    """

    def __init__(self, **kwargs):
        n = self.name
        super(OpNode, self).__init__((lambda: None, (), {}), **kwargs)
        self.name = n


class AndNode(OpNode):
    """Sequential evaluation semantics.

    Children of :class:`AndNode` will be evaluated in the order in
    which they were added as children of this node.

    """

    # Implementation notes:
    #
    # Evaluation order is enforced by only sparking the first child in
    # the call to `start`. This will allow evaluation to be sparked on
    # any grandhildren of this node according to their respecitve
    # semantics. Any other children will be evaluted in the `wait`
    # function sequentially.


    name = T.String('&')

    def start(self):

        for child in self.children_iter:
            child.start()
            break


    def wait(self):
        self.result = futures.Future()
        for child in self.children_iter:
            child.start()
            child.wait()
        self.result.set_result(None)


class OrNode(OpNode):
    """Parallel evaluation semantics

    Children of :class:`OrNode` will be evaluated in parallel, sparked
    in the order in which they were added as children of this node.

    """

    # Implementation notes:
    #
    # Evaluation is done by sparking all children, then waiting for
    # all children.

    name = T.String('|')

    def start(self):
        for child in self.children_iter:
            child.start()

    def wait(self):
        for child in self.children_iter:
            child.wait()


@delayed()
def A():
    print 'A START'
    # for i in xrange(10):
    #     print 'A', i
    time.sleep(3)
    # print 'A STOP'

@delayed()
def B():
    print 'B START'
    time.sleep(3)
    # print 'B STOP'

@delayed()
def C():
    print 'C START'
    time.sleep(3)
    # print 'C STOP'

@delayed()
def D():
    print 'D START'
    time.sleep(3)
    # print 'D STOP'

@delayed()
def F():
    print 'F START'
    time.sleep(3)
    # print 'F STOP'


def clean(G):
    H = G.copy()
    N = {}
    E = {}

    for n in H.nodes():
        node = H.node[n]['node']
        del H.node[n]['node']
        N[n] = node.name


    return H, N, E

def test():
    # node = ( A() | B() | C() )
    # node = ( A() & B() | C() )
    # node = ( A() | (B() & C()) )
    # node = ( ((A() & B()) | C()) & (D() | F()) )
    node = (A() | B() | C()) & (D() | F())

    G = node.graph
    H, N, E = clean(G)
    evaluate(G)
    nx.write_dot(H, '/tmp/test.dot')

if __name__ == '__main__':
    test()