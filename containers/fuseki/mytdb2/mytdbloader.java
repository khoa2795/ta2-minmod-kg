/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package mytdb2;

import static org.apache.jena.atlas.lib.ListUtils.toList;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Objects;
import java.util.ArrayList;

import org.apache.jena.atlas.lib.InternalErrorException;
import org.apache.jena.atlas.lib.Timer;
import org.apache.jena.cmd.ArgDecl;
import org.apache.jena.cmd.CmdException;
import org.apache.jena.graph.Node;
import org.apache.jena.graph.NodeFactory;
import org.apache.jena.query.ARQ;
import org.apache.jena.riot.Lang;
import org.apache.jena.riot.RDFLanguages;
import org.apache.jena.sparql.core.DatasetGraph;
import org.apache.jena.system.Txn;
import org.apache.jena.system.progress.MonitorOutput;
import org.apache.jena.system.progress.MonitorOutputs;
import org.apache.jena.tdb2.loader.DataLoader;
import org.apache.jena.tdb2.loader.LoaderFactory;
import org.apache.jena.tdb2.loader.base.LoaderOps;
import org.apache.jena.tdb2.loader.main.LoaderPlans;
import org.apache.jena.util.FileUtils;
import tdb2.cmdline.CmdTDB;
import tdb2.cmdline.CmdTDBGraph;

public class mytdbloader extends CmdTDBGraph {
    private static final ArgDecl argStats = new ArgDecl(ArgDecl.HasValue, "stats");
    private static final ArgDecl argLoader = new ArgDecl(ArgDecl.HasValue, "loader");
    private static final ArgDecl argSyntax = new ArgDecl(ArgDecl.HasValue, "syntax");

    private enum LoaderEnum {
        Basic, Parallel, Sequential, Light, Phased
    }

    private boolean showProgress = true;
    private boolean generateStats = false;
    private LoaderEnum loader = null;
    private Lang lang = Lang.NQUADS;

    public static void main(String... args) {
        CmdTDB.init();
        new mytdbloader(args).mainRun();
    }

    protected mytdbloader(String[] argv) {
        super(argv);
        // super.add(argStats, "Generate statistics");
        super.add(argLoader, "--loader=",
                "Loader to use: 'basic', 'phased' (default), 'sequential', 'parallel' or 'light'");
        super.add(argSyntax, "--syntax=LANG", "Syntax of data from stdin");
    }

    @Override
    protected void processModulesAndArgs() {
        super.processModulesAndArgs();

        if (contains(argLoader)) {
            String loadername = getValue(argLoader).toLowerCase();
            if (loadername.matches("basic.*"))
                loader = LoaderEnum.Basic;
            else if (loadername.matches("phas.*"))
                loader = LoaderEnum.Phased;
            else if (loadername.matches("seq.*"))
                loader = LoaderEnum.Sequential;
            else if (loadername.matches("para.*"))
                loader = LoaderEnum.Parallel;
            else if (loadername.matches("light"))
                loader = LoaderEnum.Light;
            else
                throw new CmdException("Unrecognized value for --loader: " + loadername);
        }

        if (super.contains(argStats)) {
            if (!hasValueOfTrue(argStats) && !hasValueOfFalse(argStats))
                throw new CmdException("Not a boolean value: " + getValue(argStats));
            generateStats = super.hasValueOfTrue(argStats);
        }

        if (super.graphName != null)
            lang = Lang.NTRIPLES;

        if (super.contains(argSyntax)) {
            String syntax = super.getValue(argSyntax);
            Lang lang$ = RDFLanguages.nameToLang(syntax);
            if (lang$ == null)
                throw new CmdException("Can not detemine the syntax from '" + syntax + "'");
            this.lang = lang$;
        }
    }

    @Override
    protected String getSummary() {
        return getCommandName() + "--loader= [--desc DATASET | --loc DIR] FILE ...";
    }

    @Override
    protected void exec() {
        if (isVerbose()) {
            System.out.println("Java maximum memory: " + Runtime.getRuntime().maxMemory());
            System.out.println(ARQ.getContext());
        }
        if (isVerbose())
            showProgress = true;
        if (isQuiet())
            showProgress = false;

        List<String> input_files = getPositional();
        System.out.println("input_files: " + input_files);
        if (input_files.size() != 1) {
            System.err.println("Expect a single file of URLs");
            return;
        }

        List<String> urls = new ArrayList<String>(1);

        try {
            urls = Files.readAllLines(Paths.get(input_files.get(0)),
                    java.nio.charset.StandardCharsets.UTF_8);
        } catch (IOException e) {
            System.err.println("Error reading file: " + e.getMessage());
            return;
        }

        if (urls.size() != 0)
            checkFiles(urls);

        if (graphName == null) {
            if (urls.size() == 0)
                loadQuadsStdin();
            else
                loadQuads(urls);
            return;
        }

        // There's a --graph.
        // Check/warn that there are no quads formats mentioned

        for (String url : urls) {
            Lang lang = RDFLanguages.filenameToLang(url);
            if (lang != null && !Lang.JSONLD.equals(lang) && RDFLanguages.isQuads(lang)) {
                // People think JSONLD is a single graph format.
                if (RDFLanguages.isQuads(lang)) {
                    System.err.println(
                            "Warning: Quads format given - only the default graph from the data is loaded into the graph for --graph");
                }
            }
        }

        if (urls.size() == 0)
            loadTriplesStdin();
        else
            loadTriples(graphName, urls);
    }

    // Check files exists before starting.
    private void checkFiles(List<String> urls) {
        List<String> problemFiles = toList(urls.stream()
                // Local files.
                .filter(u -> FileUtils.isFile(u))
                .map(Paths::get)
                .filter(p -> !Files.exists(p) ||
                        !Files.isRegularFile(p /* this follows links */) ||
                        !Files.isReadable(p))
                .map(Path::toString));
        if (!problemFiles.isEmpty()) {
            if (problemFiles.size() == 1)
                throw new CmdException("Can't read file : " + problemFiles.get(0));
            String str = String.join(", ", problemFiles);
            throw new CmdException("Can't read files : " + str);
        }
    }

    private void loadQuads(List<String> urls) {
        // generateStats
        execBulkLoad(super.getDatasetGraph(), null, urls, showProgress);
    }

    private void loadTriples(String graphName, List<String> urls) {
        execBulkLoad(super.getDatasetGraph(), graphName, urls, showProgress);
    }

    private long execBulkLoad(DatasetGraph dsg, String graphName, List<String> urls, boolean showProgress) {
        DataLoader loader = chooseLoader(dsg, graphName);
        long elapsed = Timer.time(() -> {
            loader.startBulk();
            loader.load(urls);
            loader.finishBulk();
        });
        return elapsed;
    }

    private long loadQuadsStdin() {
        Lang parseLang = (lang != null) ? lang : Lang.NQUADS;
        long elapsed = execBulkLoadStdin(super.getDatasetGraph(), null, parseLang, showProgress);
        return elapsed;
    }

    private long loadTriplesStdin() {
        Lang parseLang = (lang != null) ? lang : Lang.NTRIPLES;
        long elapsed = execBulkLoadStdin(super.getDatasetGraph(), graphName, parseLang, showProgress);
        return elapsed;
    }

    private long execBulkLoadStdin(DatasetGraph dsg, String graphName, Lang syntax, boolean showProgress) {
        DataLoader loader = chooseLoader(dsg, graphName);
        long elapsed = Timer.time(() -> {
            loader.startBulk();
            loader.loadFromInputStream("(stdin)", System.in, syntax);
            loader.finishBulk();
        });
        return elapsed;
    }

    /** Decide on the bulk loader. */
    private DataLoader chooseLoader(DatasetGraph dsg, String graphName) {
        Objects.requireNonNull(dsg);
        Node gn = null;
        if (graphName != null)
            gn = NodeFactory.createURI(graphName);

        LoaderEnum useLoader = loader;
        if (useLoader == null) {
            // Default choice - phased if empty. basic if not.
            boolean isEmpty = Txn.calculateRead(dsg, () -> dsg.isEmpty());
            if (isEmpty)
                useLoader = LoaderEnum.Phased;
            else
                useLoader = LoaderEnum.Basic;
        }

        MonitorOutput output = isQuiet() ? MonitorOutputs.nullOutput() : LoaderOps.outputToLog();
        DataLoader loader = createLoader(useLoader, dsg, gn, output);
        if (output != null)
            output.print("Loader = %s", loader.getClass().getSimpleName());
        return loader;
    }

    private DataLoader createLoader(LoaderEnum useLoader, DatasetGraph dsg, Node gn, MonitorOutput output) {
        switch (useLoader) {
            case Phased:
                return LoaderFactory.phasedLoader(dsg, gn, output);
            case Parallel:
                return LoaderFactory.parallelLoader(dsg, gn, output);
            case Sequential:
                return LoaderFactory.sequentialLoader(dsg, gn, output);
            case Light:
                return LoaderFactory.createLoader(LoaderPlans.loaderPlanLight, dsg, output);
            case Basic:
                return LoaderFactory.basicLoader(dsg, gn, output);
            default:
                throw new InternalErrorException("Unrecognized loader: " + useLoader);
        }
    }
}
